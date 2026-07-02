#!/usr/bin/env python3
"""Import a RisuAI character card for Hermes + risu-display.

Accepts .charx zips and JPEG-wrapped cards (RisuAI CharX-JPEG: JPEG image
with the zip appended). Extracts emotion/scene assets into the risu-display
convention (assets/portraits/<character>/<emotion>.<ext>,
assets/scenes/<character>/<name>.<ext>) and generates a hermes-agent
personality from the card's persona fields, so that `/personality <name>`
turns a Hermes session into the imported character.

Usage:
    python3 tools/import_charx.py character.charx
    python3 tools/import_charx.py character.jpeg --install
    python3 tools/import_charx.py card --toggle langtoggle=0 --reinstall
    python3 tools/import_charx.py --selftest

Only the Python standard library is required. PyYAML, if available, is used
to validate config.yaml after --install.
"""

import argparse
import base64
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTRAIT_TYPES = {"emotion"}
ICON_TYPES = {"icon", "main"}
BACKGROUND_TYPES = {"background"}
RISU_ASSET_TYPE = "x-risu-asset"  # RisuAI's generic asset type
KNOWN_MACRO = re.compile(r"\{\{(char|user|bot)\}\}", re.IGNORECASE)
ANY_MACRO = re.compile(r"\{\{[^{}]*\}\}")
DECORATOR_LINE = re.compile(r"^@@\S.*$", re.M)
IMG_TAG = re.compile(r"<img\s[^>]*>", re.IGNORECASE)


def log(msg):
    print(msg)


def warn(msg):
    print("warning: " + msg, file=sys.stderr)


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def sanitize_component(name):
    """Make an asset name safe as a single path component."""
    name = (name or "").strip().lower()
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w .\-()가-힣ぁ-ヿ一-鿿]", "_", name)
    name = name.strip(". ")
    return name or "unnamed"


def normalize_tag(name):
    """Canonical form for matching asset names against card tag lists."""
    return re.sub(r"\s+", " ", (name or "").strip().lower().replace("_", " "))


def strip_char_prefix(name, char_name):
    """Remove a leading 'CharName_' or 'CharName ' from an asset name."""
    n = (name or "").strip()
    for sep in ("_", " "):
        prefix = (char_name + sep).lower()
        if n.lower().startswith(prefix):
            return n[len(prefix):].strip()
    return n


# ------------------------------------------------------------------ card IO --

def load_card(charx_path):
    """Open a .charx zip or a JPEG-wrapped card (zip appended to the image)."""
    try:
        zf = zipfile.ZipFile(charx_path)
    except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError) as e:
        head = b""
        try:
            head = open(charx_path, "rb").read(8)
        except OSError:
            pass
        if head[:4] == b"\x89PNG":
            die("%s is a PNG character card (base64 in a tEXt chunk) — not "
                "supported. Export the character from RisuAI as CHARX instead."
                % charx_path)
        die("cannot open %s as a character card: %s" % (charx_path, e))
    try:
        raw = zf.read("card.json")
    except KeyError:
        die("no card.json at the root of %s — not a CharX archive" % charx_path)
    try:
        card = json.loads(raw)
    except json.JSONDecodeError as e:
        die("card.json is not valid JSON: %s" % e)
    spec = card.get("spec", "")
    if spec != "chara_card_v3":
        die("unsupported card spec %r — this importer requires chara_card_v3 "
            "(export the character from RisuAI as CHARX)" % spec)
    data = card.get("data")
    if not isinstance(data, dict) or not (data.get("name") or "").strip():
        die("card.json has no data.name — cannot determine the character")
    return zf, data


def read_asset_bytes(zf, uri):
    """Resolve one card.json asset URI to bytes, or None if unsupported."""
    if uri.startswith("embeded://") or uri.startswith("embedded://"):
        inner = uri.split("://", 1)[1]
        try:
            return zf.read(inner)
        except KeyError:
            warn("asset path %s not found inside the archive; skipped" % inner)
            return None
    if uri.startswith("data:"):
        try:
            return base64.b64decode(uri.split(",", 1)[1])
        except (IndexError, ValueError) as e:
            warn("undecodable data: URI (%s); skipped" % e)
            return None
    if uri.startswith("http://") or uri.startswith("https://"):
        warn("remote asset %s skipped (not downloaded); add it manually" % uri)
        return None
    if uri.startswith("ccdefault:"):
        return None  # application default; risu-display's own fallback covers it
    warn("unknown asset URI scheme %r; skipped" % uri.split(":", 1)[0])
    return None


def sniff_ext(blob, declared):
    """Correct a declared extension against the actual image bytes."""
    if blob[:2] == b"\xff\xd8":
        actual = "jpg"
    elif blob[:4] == b"\x89PNG":
        actual = "png"
    elif blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        actual = "webp"
    elif blob[:4] in (b"GIF8",):
        actual = "gif"
    else:
        return declared
    declared_norm = "jpg" if declared == "jpeg" else declared
    if declared_norm != actual:
        warn("asset declared .%s but bytes are %s — saving as .%s"
             % (declared, actual, actual))
    return actual


def write_asset(dest, blob, force):
    if dest.exists() and not force:
        log("  keep   %s (exists; use --force to overwrite)" % dest)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    log("  write  %s" % dest)
    return True


# --------------------------------------------------- asset protocol parsing --

def parse_asset_taglists(book):
    """Find the card's own asset tag lists (RisuAI 'Image Asset Protocol'
    lorebook entry). Returns (emotion_tags, scene_tags, entry_index) with
    tags normalized; entry_index is None when no such entry exists."""
    for idx, entry in enumerate((book or {}).get("entries") or []):
        content = entry.get("content") or ""
        if "tag list" not in content.lower():
            continue
        emotions, scenes = [], []
        sections = re.findall(r"^#{2,4}\s*(.+?)\s*$\n(.*?)(?=^#{2,4}\s|\Z)",
                              content, re.M | re.S)
        for header, body in sections:
            if "tag list" not in header.lower():
                continue
            lines = [l for l in body.split("\n")
                     if l.strip() and not re.search(r"example", l, re.I)]
            tags = [normalize_tag(t) for l in lines for t in l.split(",")
                    if normalize_tag(t)]
            if re.search(r"sexual|scene|nsfw", header, re.I):
                scenes.extend(tags)
            else:
                emotions.extend(tags)
        if emotions or scenes:
            return emotions, scenes, idx
    return [], [], None


def extract_assets(zf, data, slug, assets_dir, force, taglists):
    """Copy card assets into the risu-display layout.
    Returns (emotion_names, scene_names)."""
    emotion_tags, scene_tags, _ = taglists
    emotion_set, scene_set = set(emotion_tags), set(scene_tags)
    char_name = (data.get("name") or "").strip()
    emotions, scenes = [], []
    have_default = False

    def add_portrait(tag, blob, ext, force_write=False):
        nonlocal have_default
        dest = assets_dir / "portraits" / slug / (sanitize_component(tag) + "." + ext)
        write_asset(dest, blob, force or force_write)
        if tag == "default":
            have_default = True
        elif tag not in emotions:
            emotions.append(tag)

    for asset in data.get("assets", []) or []:
        a_type = (asset.get("type") or "").lower()
        uri = asset.get("uri") or ""
        raw_name = asset.get("name") or ""
        blob = read_asset_bytes(zf, uri)
        if blob is None:
            continue
        ext = sniff_ext(blob, sanitize_component(asset.get("ext") or "png"))
        if a_type in PORTRAIT_TYPES:
            add_portrait(normalize_tag(raw_name), blob, ext)
        elif a_type in ICON_TYPES:
            dest = assets_dir / "portraits" / slug / ("default." + ext)
            if write_asset(dest, blob, force or not have_default):
                have_default = True
        elif a_type in BACKGROUND_TYPES:
            dest = assets_dir / "scenes" / slug / (sanitize_component(raw_name) + "." + ext)
            write_asset(dest, blob, force)
        elif a_type == RISU_ASSET_TYPE:
            tag = normalize_tag(strip_char_prefix(raw_name, char_name))
            if tag in scene_set:
                dest = assets_dir / "scenes" / slug / (sanitize_component(tag) + "." + ext)
                write_asset(dest, blob, force)
                if tag not in scenes:
                    scenes.append(tag)
            else:
                if emotion_set and tag not in emotion_set:
                    if emotion_set or scene_set:
                        warn("asset %r is in neither tag list; treating as emotion" % tag)
                add_portrait(tag, blob, ext)
        else:
            warn("asset type %r (%s) has no risu-display slot; skipped"
                 % (a_type, raw_name))

    if not have_default and emotions:
        # Anchor the fallback chain on the first emotion.
        first = next((assets_dir / "portraits" / slug).glob(
            sanitize_component(emotions[0]) + ".*"), None)
        if first:
            copy = first.with_name("default" + first.suffix)
            if not copy.exists():
                shutil.copyfile(first, copy)
                log("  write  %s (copied from %s)" % (copy, first.name))
    return emotions, scenes


# ------------------------------------------------------------------ macros --

TOGGLE_IF = re.compile(
    r"\{\{#if \{\{equal::\{\{getglobalvar::(?:toggle_)?(\w+)\}\}::([^{}]*)\}\}\}\}")
ENDIF = "{{/if}}"


def parse_toggle_labels(data):
    """RisuAI stores human-readable toggle labels in extensions.risuai.toggles
    ('name=label' per line)."""
    raw = ((data.get("extensions") or {}).get("risuai") or {}).get("toggles") or ""
    labels = {}
    for line in raw.split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            labels[k.strip()] = v.strip()
    return labels


def resolve_toggles(text, choices, seen=None):
    """Evaluate RisuAI toggle conditionals, keeping only the chosen branch.
    {{#if {{equal::{{getglobalvar::toggle_X}}::V}}}}...{{/if}} keeps the body
    when V equals the choice for X (default '1' = toggle on). Non-nested."""
    out, pos = [], 0
    while True:
        m = TOGGLE_IF.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        end = text.find(ENDIF, m.end())
        if end == -1:  # unbalanced — leave the marker for the leftover pass
            out.append(text[m.start():m.end()])
            pos = m.end()
            continue
        var, val = m.group(1), m.group(2)
        if seen is not None:
            seen.setdefault(var, set()).add(val)
        if val == choices.get(var, "1"):
            out.append(text[m.end():end])
        pos = end + len(ENDIF)
    return "".join(out)


def substitute_macros(text, char_name, choices=None, removed=None):
    """Toggle branches -> {{char}}/{{user}} -> strip remaining macros.
    Unknown macros (possibly nested) are removed innermost-first; what was
    removed is collected into `removed` so the caller can report it."""
    out = resolve_toggles(text or "", choices or {})

    def repl(m):
        word = m.group(1).lower()
        return char_name if word in ("char", "bot") else "the user"
    out = KNOWN_MACRO.sub(repl, out)

    prev = None
    while out != prev:
        prev = out
        for m in ANY_MACRO.findall(out):
            if removed is not None:
                removed.add(m)
        out = ANY_MACRO.sub("", out)
    return out


# ----------------------------------------------------------------- persona --

def render_lorebook(book, sub, protocol_idx):
    constant_parts, keyed_parts = [], []
    for i, entry in enumerate((book or {}).get("entries") or []):
        if i == protocol_idx or entry.get("enabled") is False:
            continue
        content = DECORATOR_LINE.sub("", sub(entry.get("content", ""))).strip()
        if not content:
            continue
        keys = [k for k in (entry.get("keys") or []) if k and k.strip()]
        if entry.get("constant") or not keys:
            constant_parts.append(content)
        else:
            keyed_parts.append("- When the conversation touches on %s:\n  %s"
                              % (", ".join('"%s"' % k for k in keys),
                                 content.replace("\n", "\n  ")))
    return constant_parts, keyed_parts


def protocol_usage_notes(book, sub, protocol_idx):
    """Carry over the card's own asset-usage rules (priority rules, tag
    interpretations), dropping the RisuAI-specific format/tag-list sections
    that the generated Rich Output section replaces."""
    if protocol_idx is None:
        return ""
    content = sub((book["entries"][protocol_idx].get("content") or ""))
    content = DECORATOR_LINE.sub("", content)
    kept = []
    for header, body in re.findall(r"^(#{2,4}\s*.+?)\s*$\n(.*?)(?=^#{2,4}\s|\Z)",
                                   content, re.M | re.S):
        h = header.lower()
        if "tag list" in h or "format" in h:
            continue
        body = IMG_TAG.sub("", body).strip()
        if body:  # skip pure container headers (e.g. "## X's Image Asset Protocol")
            kept.append(header.strip() + "\n" + body)
    return "\n\n".join(kept)


def build_persona(data, slug, emotions, scenes, choices):
    name = data["name"].strip()
    removed = set()
    sub = lambda t: substitute_macros(t, name, choices, removed)
    field = lambda key: sub(data.get(key) or "").strip()

    sections = ["# %s — persona (imported from RisuAI)" % name, ""]
    sections.append("You are roleplaying as **%s**. Stay in character at all times." % name)
    sections.append("")

    for heading, key in (("Description", "description"),
                         ("Personality", "personality"),
                         ("Scenario", "scenario"),
                         ("Instructions", "system_prompt")):
        text = field(key)
        if text:
            sections += ["## " + heading, "", text, ""]

    first = field("first_mes")
    if first:
        sections += ["## Opening",
                     "",
                     "At the start of a new conversation, greet in this style:",
                     "",
                     "> " + first.replace("\n", "\n> "),
                     ""]
    alts = [sub(g).strip() for g in data.get("alternate_greetings") or []
            if g and g.strip()]
    if alts:
        sections += ["Alternative openings you may use instead:", ""]
        sections += ["- " + a.replace("\n", " ") for a in alts]
        sections.append("")

    book = data.get("character_book") or {}
    _, _, protocol_idx = parse_asset_taglists(book)
    constant_parts, keyed_parts = render_lorebook(book, sub, protocol_idx)
    if constant_parts or keyed_parts:
        sections += ["## World & lore", ""]
        sections += [p + "\n" for p in constant_parts]
        if keyed_parts:
            sections += ["Bring in this lore only when relevant:", ""]
            sections += keyed_parts
            sections.append("")

    notes = protocol_usage_notes(book, sub, protocol_idx)
    sections += rich_output_section(name, slug, emotions, scenes, notes)

    if removed:
        warn("RisuAI macros removed from persona text: %s"
             % ", ".join(sorted(removed)[:8])
             + (" …" if len(removed) > 8 else ""))
    return "\n".join(sections).rstrip() + "\n"


def rich_output_section(name, slug, emotions, scenes, notes):
    emotion_list = ", ".join(emotions) if emotions else "default"
    out = [
        "## Rich output (risu-display)",
        "",
        "The user's WebUI renders special fenced code blocks as rich content",
        "(the `risu-rich-content` skill documents the full syntax). Follow these rules:",
        "",
        "- Show %s's current emotion as a large centered illustration with a" % name,
        "  `risu-emotion` block placed in the middle of the message, at the moment",
        "  it depicts. Keep all dialogue and narration as plain prose — do NOT",
        "  wrap dialogue in risu-dialogue bubbles.",
        "- One emotion block per emotional beat; don't repeat the same emotion",
        "  twice in one message.",
        "- Available emotions: %s." % emotion_list,
        "  Use only these; anything else falls back to the default portrait.",
        "",
        "Example:",
        "",
        "```risu-emotion",
        "character: %s" % slug,
        "emotion: %s" % (emotions[0] if emotions else "default"),
        "```",
        "",
    ]
    if scenes:
        out += [
            "- Scene/action images live at `scenes/%s/<tag>.webp`. When a listed" % slug,
            "  scene tag matches the situation, show it with:",
            "",
            "```risu-image",
            "path: scenes/%s/%s.webp" % (slug, scenes[0]),
            "size: xlarge",
            "```",
            "",
            "- Available scene tags: %s." % ", ".join(scenes),
            "",
        ]
    if notes:
        out += ["### Card's own asset-usage rules (imported)", "", notes, ""]
    return out


# ------------------------------------------------------------------ install --

def yaml_block_scalar(text, indent):
    pad = " " * indent
    lines = [pad + line if line.strip() else "" for line in text.split("\n")]
    return "|\n" + "\n".join(lines)


def personality_key(slug):
    return re.sub(r"\s+", "-", slug)


def build_yaml_snippet(slug, persona_text):
    key = personality_key(slug)
    return ("agent:\n"
            "  personalities:\n"
            "    %s: %s\n" % (key, yaml_block_scalar(persona_text.rstrip(), 6)))


def remove_personality_block(text, key):
    """Drop an existing '    <key>: |' block (its indented body included)."""
    lines = text.split("\n")
    out, i, dropped = [], 0, False
    start_re = re.compile(r"^    %s:" % re.escape(key))
    while i < len(lines):
        if not dropped and start_re.match(lines[i]):
            dropped = True
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith("      ")):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), dropped


def install_personality(slug, persona_text, hermes_home, reinstall=False):
    """Insert agent.personalities.<key> into config.yaml, preserving the file."""
    key = personality_key(slug)
    config = hermes_home / "config.yaml"
    entry = "    %s: %s\n" % (key, yaml_block_scalar(persona_text.rstrip(), 6))

    if not config.exists():
        warn("%s not found — paste the generated .personality.yaml manually" % config)
        return False
    text = config.read_text(encoding="utf-8")
    if re.search(r"^    %s:" % re.escape(key), text, re.M):
        if not reinstall:
            warn("personality %r already exists in %s; use --reinstall to replace it"
                 % (key, config))
            return False
        text, dropped = remove_personality_block(text, key)
        if dropped:
            log("  replacing existing personality %r" % key)

    lines = text.split("\n")
    insert_at = None
    agent_at = None
    for i, line in enumerate(lines):
        if re.match(r"^agent:\s*(#.*)?$", line):
            agent_at = i
        elif agent_at is not None and re.match(r"^  personalities:\s*(#.*)?$", line):
            insert_at = i + 1
            break
        elif agent_at is not None and line and not line.startswith(" ") and i > agent_at:
            break  # left the agent block

    if insert_at is not None:
        lines[insert_at:insert_at] = entry.rstrip("\n").split("\n")
        new_text = "\n".join(lines)
    elif agent_at is not None:
        block = "  personalities:\n" + entry
        lines[agent_at + 1:agent_at + 1] = block.rstrip("\n").split("\n")
        new_text = "\n".join(lines)
    else:
        new_text = text.rstrip("\n") + "\n\nagent:\n  personalities:\n" + entry

    try:
        import yaml  # optional, for validation only
        parsed = yaml.safe_load(new_text)
        assert parsed["agent"]["personalities"][key].strip()
    except ImportError:
        pass
    except Exception as e:
        warn("config.yaml merge failed validation (%s); leaving it unchanged — "
             "paste the .personality.yaml snippet manually" % e)
        return False

    backup = config.with_suffix(".yaml.bak")
    shutil.copyfile(config, backup)
    config.write_text(new_text, encoding="utf-8")
    log("  merged personality %r into %s (backup: %s)" % (key, config, backup.name))
    return True


# ------------------------------------------------------------------- driver --

def import_charx(charx_path, assets_dir, personas_dir, force, install,
                 hermes_home, toggles=None, reinstall=False):
    zf, data = load_card(charx_path)
    name = data["name"].strip()
    slug = name.lower()
    log("importing %r (folder: portraits/%s)" % (name, slug))

    choices = dict(toggles or {})
    labels = parse_toggle_labels(data)
    seen = {}
    for key in ("description", "personality", "scenario", "system_prompt", "first_mes"):
        resolve_toggles(data.get(key) or "", choices, seen)
    for entry in (data.get("character_book") or {}).get("entries") or []:
        resolve_toggles(entry.get("content") or "", choices, seen)
    for var, vals in sorted(seen.items()):
        kept = choices.get(var, "1")
        log("  toggle %s (%s): keeping branch %s of %s — override with --toggle %s=<v>"
            % (var, labels.get(var, "no label"), kept, sorted(vals), var))

    taglists = parse_asset_taglists(data.get("character_book") or {})
    if taglists[2] is not None:
        log("  using card's own tag lists: %d emotions, %d scenes"
            % (len(taglists[0]), len(taglists[1])))
    emotions, scenes = extract_assets(zf, data, slug, assets_dir, force, taglists)

    persona_text = build_persona(data, slug, emotions, scenes, choices)
    personas_dir.mkdir(parents=True, exist_ok=True)
    persona_md = personas_dir / (slug + ".md")
    persona_md.write_text(persona_text, encoding="utf-8")
    log("  write  %s" % persona_md)
    snippet = personas_dir / (slug + ".personality.yaml")
    snippet.write_text(build_yaml_snippet(slug, persona_text), encoding="utf-8")
    log("  write  %s" % snippet)

    installed = install and install_personality(slug, persona_text, hermes_home,
                                                reinstall)

    key = personality_key(slug)
    log("")
    log("done: %d emotions, %d scenes. next steps:" % (len(emotions), len(scenes)))
    if not installed:
        log("  1. merge %s into ~/.hermes/config.yaml (under agent.personalities)"
            % snippet.name)
        step = 2
    else:
        step = 1
    log("  %d. make sure %s is the extension's asset dir served at "
        "/extensions/risu-display/assets/" % (step, assets_dir))
    log("  %d. in a Hermes session: /personality %s" % (step + 1, key))
    return slug, emotions, scenes


# ---------------------------------------------------------------- selftest --

def _make_charx(path, spec="chara_card_v3", name="Mira", assets=None,
                files=None, data_extra=None, jpeg_prefix=False):
    data = {
        "name": name,
        "description": "A wandering star-charter. {{char}} maps skies for {{user}}.",
        "personality": "curious, wry",
        "scenario": "A drifting observatory.",
        "first_mes": "Oh — a visitor? {{user}}, come look at this.",
        "assets": assets if assets is not None else [],
        "character_book": {"entries": [
            {"keys": [], "constant": True, "enabled": True,
             "content": "The observatory orbits a dying star."},
            {"keys": ["sextant"], "enabled": True,
             "content": "{{char}}'s sextant is haunted."},
        ]},
    }
    if data_extra:
        data.update(data_extra)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("card.json",
                   json.dumps({"spec": spec, "spec_version": "3.0", "data": data}))
        for inner, blob in (files or {}).items():
            z.writestr(inner, blob)
    if jpeg_prefix:
        raw = path.read_bytes()
        path.write_bytes(b"\xff\xd8\xe0fake-jpeg-data" + raw)


SVG = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        assets_dir, personas_dir = td / "assets", td / "personas"

        # 1. legacy emotion-typed assets, Korean names, duplicates
        cx = td / "ok.charx"
        _make_charx(cx, name="Star Chart Mira",
                    files={"a/joy.svg": SVG, "a/joy2.svg": SVG, "a/i.svg": SVG},
                    assets=[
            {"type": "emotion", "uri": "embeded://a/joy.svg", "name": "Joy", "ext": "svg"},
            {"type": "emotion", "uri": "embeded://a/joy2.svg", "name": "joy", "ext": "svg"},
            {"type": "emotion", "uri": "embeded://a/joy.svg", "name": "수줍음", "ext": "svg"},
            {"type": "emotion", "uri": "ccdefault:", "name": "ghost", "ext": "png"},
            {"type": "icon", "uri": "embeded://a/i.svg", "name": "main", "ext": "svg"},
        ])
        slug, emotions, scenes = import_charx(cx, assets_dir, personas_dir,
                                              False, False, td)
        assert slug == "star chart mira" and emotions == ["joy", "수줍음"], (slug, emotions)
        pdir = assets_dir / "portraits" / slug
        assert (pdir / "joy.svg").exists() and (pdir / "default.svg").exists()
        persona = (personas_dir / (slug + ".md")).read_text(encoding="utf-8")
        assert "{{char}}" not in persona and "sextant" in persona
        assert "risu-emotion" in persona and "star-chart-mira" not in persona
        yml = (personas_dir / (slug + ".personality.yaml")).read_text(encoding="utf-8")
        assert "star-chart-mira: |" in yml

        # 2. Laura-style: JPEG wrapper, x-risu-asset + tag lists, prefix strip,
        #    normalization (underscore/trailing space), ext mismatch, toggles
        protocol = ("@@depth 0\n## {{char}}'s Image Asset Protocol\n"
                    "### Tag Rule\n- Use tags for {{char}} only\n"
                    "### Format\n- Asset format : `<img src='Lau_Tag'>`\n"
                    "### Tag list\nsmile, evil_smile\n"
                    "  - Example: `<img src='Lau_smile'>`\n"
                    "### Sexual scene tag list\nafter sex, wet clothes\n"
                    "- Example : `<img src='Lau_after sex'>`\n"
                    "### Additional Important Usage Notes\n"
                    "- `wet clothes`: clothes are wet\n")
        desc = ("{{#if {{equal::{{getglobalvar::toggle_kor}}::1}}}}한국어 설명{{/if}}"
                "{{#if {{equal::{{getglobalvar::toggle_kor}}::0}}}}English desc{{/if}}")
        cx2 = td / "laura.charx"
        _make_charx(cx2, name="Lau", jpeg_prefix=True,
                    files={"a/s.webp": WEBP, "a/e.webp": WEBP, "a/x.webp": WEBP,
                           "a/w.webp": WEBP, "a/h.webp": WEBP, "a/i.webp": WEBP},
                    data_extra={
                        "description": desc, "first_mes": "",
                        "extensions": {"risuai": {"toggles": "kor=한출"}},
                        "character_book": {"entries": [
                            {"keys": [""], "constant": True, "enabled": True,
                             "content": protocol}]},
                    },
                    assets=[
            {"type": "x-risu-asset", "uri": "embeded://a/s.webp", "name": "Lau_smile", "ext": "webp"},
            {"type": "x-risu-asset", "uri": "embeded://a/e.webp", "name": "Lau_evil smile", "ext": "webp"},
            {"type": "x-risu-asset", "uri": "embeded://a/x.webp", "name": "Lau_after sex ", "ext": "webp"},
            {"type": "x-risu-asset", "uri": "embeded://a/w.webp", "name": "Lau_Wet_Clothes", "ext": "webp"},
            {"type": "x-risu-asset", "uri": "embeded://a/h.webp", "name": "Lau_hidden gem", "ext": "webp"},
            {"type": "icon", "uri": "embeded://a/i.webp", "name": "main", "ext": "png"},
        ])
        slug2, emo2, scn2 = import_charx(cx2, assets_dir, personas_dir, False, False, td)
        assert emo2 == ["smile", "evil smile", "hidden gem"], emo2
        assert scn2 == ["after sex", "wet clothes"], scn2
        p2 = assets_dir / "portraits" / "lau"
        assert (p2 / "evil smile.webp").exists() and (p2 / "default.webp").exists()
        assert not (p2 / "default.png").exists()  # sniffed webp, not declared png
        assert (assets_dir / "scenes" / "lau" / "wet clothes.webp").exists()
        persona2 = (personas_dir / "lau.md").read_text(encoding="utf-8")
        assert "한국어 설명" in persona2 and "English desc" not in persona2
        assert "Image Asset Protocol" not in persona2  # replaced, not inlined
        assert "clothes are wet" in persona2           # usage notes carried over
        assert "@@depth" not in persona2 and "<img" not in persona2
        assert "scenes/lau/after sex.webp" in persona2

        # toggle override -> English branch
        import_charx(cx2, td / "a2", td / "p2", False, False, td,
                     toggles={"kor": "0"})
        persona2e = (td / "p2" / "lau.md").read_text(encoding="utf-8")
        assert "English desc" in persona2e and "한국어 설명" not in persona2e

        # 3. config.yaml install + --reinstall
        cfg = td / "config.yaml"
        cfg.write_text("agent:\n  model: foo\n  personalities:\n"
                       "    helpful: \"Be helpful.\"\nother: 1\n", encoding="utf-8")
        assert install_personality("lau", "Persona body\nline two", td)
        assert not install_personality("lau", "x", td)  # duplicate refused
        assert install_personality("lau", "New body", td, reinstall=True)
        merged = cfg.read_text(encoding="utf-8")
        assert "New body" in merged and "Persona body" not in merged
        assert "helpful" in merged and "other: 1" in merged

        # 4. v2 card rejected with guidance
        cx3 = td / "v2.charx"
        _make_charx(cx3, spec="chara_card_v2")
        try:
            import_charx(cx3, assets_dir, personas_dir, False, False, td)
        except SystemExit:
            pass
        else:
            raise AssertionError("v2 card was not rejected")

    print("selftest OK")


def parse_toggle_args(pairs):
    toggles = {}
    for p in pairs or []:
        if "=" not in p:
            die("--toggle expects name=value, got %r" % p)
        k, v = p.split("=", 1)
        toggles[k.strip().removeprefix("toggle_")] = v.strip()
    return toggles


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("charx", nargs="?",
                   help="path to the card (.charx zip or CharX-JPEG)")
    p.add_argument("--assets-dir", type=Path, default=REPO_ROOT / "assets",
                   help="risu-display assets dir (default: this repo's assets/)")
    p.add_argument("--personas-dir", type=Path, default=REPO_ROOT / "personas",
                   help="output dir for the generated persona (default: personas/)")
    p.add_argument("--hermes-home", type=Path, default=Path.home() / ".hermes",
                   help="Hermes home for --install (default: ~/.hermes)")
    p.add_argument("--install", action="store_true",
                   help="merge the personality into <hermes-home>/config.yaml")
    p.add_argument("--reinstall", action="store_true",
                   help="with --install, replace an existing personality entry")
    p.add_argument("--toggle", action="append", metavar="NAME=VALUE",
                   help="pick a RisuAI toggle branch (default: every toggle=1)")
    p.add_argument("--force", action="store_true", help="overwrite existing assets")
    p.add_argument("--selftest", action="store_true", help="run built-in tests")
    args = p.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.charx:
        p.error("card file required (or --selftest)")
    import_charx(Path(args.charx), args.assets_dir, args.personas_dir,
                 args.force, args.install, args.hermes_home,
                 toggles=parse_toggle_args(args.toggle), reinstall=args.reinstall)


if __name__ == "__main__":
    main()
