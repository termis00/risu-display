#!/usr/bin/env python3
"""Import a RisuAI .charx character card for Hermes + risu-display.

Extracts emotion/icon/background assets into the risu-display asset
convention (assets/portraits/<character>/<emotion>.<ext>) and generates a
hermes-agent personality from the card's persona fields, so that
`/personality <name>` turns a Hermes session into the imported character.

Usage:
    python3 tools/import_charx.py character.charx
    python3 tools/import_charx.py character.charx --install
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
KNOWN_MACRO = re.compile(r"\{\{(char|user|bot)\}\}", re.IGNORECASE)
OTHER_MACRO = re.compile(r"\{\{[^{}]+\}\}")


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


def load_card(charx_path):
    try:
        zf = zipfile.ZipFile(charx_path)
    except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError) as e:
        die("cannot open %s as a .charx zip: %s" % (charx_path, e))
    try:
        raw = zf.read("card.json")
    except KeyError:
        die("no card.json at the root of %s — not a valid .charx" % charx_path)
    try:
        card = json.loads(raw)
    except json.JSONDecodeError as e:
        die("card.json is not valid JSON: %s" % e)
    spec = card.get("spec", "")
    if spec != "chara_card_v3":
        die("unsupported card spec %r — .charx requires chara_card_v3 "
            "(export the character from RisuAI as .charx)" % spec)
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


def write_asset(dest, blob, force):
    if dest.exists() and not force:
        log("  keep   %s (exists; use --force to overwrite)" % dest)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    log("  write  %s" % dest)
    return True


def extract_assets(zf, data, slug, assets_dir, force):
    """Copy card assets into the risu-display layout. Returns emotion names."""
    emotions = []
    have_default = False
    for asset in data.get("assets", []) or []:
        a_type = (asset.get("type") or "").lower()
        uri = asset.get("uri") or ""
        name = sanitize_component(asset.get("name"))
        ext = sanitize_component(asset.get("ext") or "png")
        blob = read_asset_bytes(zf, uri)
        if blob is None:
            continue
        if a_type in PORTRAIT_TYPES:
            dest = assets_dir / "portraits" / slug / (name + "." + ext)
            write_asset(dest, blob, force)
            if name == "default":
                have_default = True
            elif name not in emotions:
                emotions.append(name)
        elif a_type in ICON_TYPES:
            dest = assets_dir / "portraits" / slug / ("default." + ext)
            if write_asset(dest, blob, force or not have_default):
                have_default = True
        elif a_type in BACKGROUND_TYPES:
            dest = assets_dir / "scenes" / slug / (name + "." + ext)
            write_asset(dest, blob, force)
        else:
            warn("asset type %r (%s) has no risu-display slot; skipped" % (a_type, name))
    if not have_default and emotions:
        # Anchor the fallback chain on the first emotion.
        first = next((assets_dir / "portraits" / slug).glob(emotions[0] + ".*"), None)
        if first:
            copy = first.with_name("default" + first.suffix)
            if not copy.exists():
                shutil.copyfile(first, copy)
                log("  write  %s (copied from %s)" % (copy, first.name))
    return emotions


def substitute_macros(text, char_name):
    def repl(m):
        word = m.group(1).lower()
        return char_name if word in ("char", "bot") else "the user"
    out = KNOWN_MACRO.sub(repl, text or "")
    leftover = sorted(set(OTHER_MACRO.findall(out)))
    if leftover:
        warn("unhandled RisuAI macros left as-is: %s" % ", ".join(leftover))
    return out


def render_lorebook(book, char_name):
    constant_parts, keyed_parts = [], []
    for entry in (book or {}).get("entries", []) or []:
        if entry.get("enabled") is False:
            continue
        content = substitute_macros(entry.get("content", ""), char_name).strip()
        if not content:
            continue
        keys = [k for k in (entry.get("keys") or []) if k]
        if entry.get("constant") or not keys:
            constant_parts.append(content)
        else:
            keyed_parts.append("- When the conversation touches on %s:\n  %s"
                              % (", ".join('"%s"' % k for k in keys),
                                 content.replace("\n", "\n  ")))
    return constant_parts, keyed_parts


def build_persona(data, slug, emotions):
    name = data["name"].strip()
    sub = lambda key: substitute_macros(data.get(key, ""), name).strip()
    sections = ["# %s — persona (imported from RisuAI)" % name, ""]
    sections.append("You are roleplaying as **%s**. Stay in character at all times." % name)
    sections.append("")

    for heading, key in (("Description", "description"),
                         ("Personality", "personality"),
                         ("Scenario", "scenario"),
                         ("Instructions", "system_prompt")):
        text = sub(key)
        if text:
            sections += ["## " + heading, "", text, ""]

    first = sub("first_mes")
    if first:
        sections += ["## Opening",
                     "",
                     "At the start of a new conversation, greet in this style:",
                     "",
                     "> " + first.replace("\n", "\n> "),
                     ""]
    alts = [substitute_macros(g, name).strip()
            for g in data.get("alternate_greetings") or [] if g and g.strip()]
    if alts:
        sections += ["Alternative openings you may use instead:", ""]
        sections += ["- " + a.replace("\n", " ") for a in alts]
        sections.append("")

    constant_parts, keyed_parts = render_lorebook(data.get("character_book"), name)
    if constant_parts or keyed_parts:
        sections += ["## World & lore", ""]
        sections += [p + "\n" for p in constant_parts]
        if keyed_parts:
            sections += ["Bring in this lore only when relevant:", ""]
            sections += keyed_parts
            sections.append("")

    sections += RICH_OUTPUT_SECTION(name, slug, emotions)
    return "\n".join(sections).rstrip() + "\n"


def RICH_OUTPUT_SECTION(name, slug, emotions):
    emotion_list = ", ".join(emotions) if emotions else "default"
    return [
        "## Rich output (risu-display)",
        "",
        "The user's WebUI renders special fenced code blocks as rich content",
        "(the `risu-rich-content` skill documents the full syntax). Follow these rules:",
        "",
        "- Wrap every in-character line of %s in a `risu-dialogue` block with" % name,
        "  `speaker: %s` and an `emotion:` matching the current mood." % name,
        "  Keep narration as plain prose outside the block.",
        "- Available emotions for %s: %s." % (name, emotion_list),
        "  Use only these; anything else falls back to the default portrait.",
        "- On a scene or location change, open the message with a `risu-scene` block.",
        "- Show stat/resource changes with `risu-status`, inventories and quest",
        "  info with `risu-panel`.",
        "- Emit each block complete, in one piece.",
        "",
        "Example:",
        "",
        "```risu-dialogue",
        "speaker: %s" % name,
        "emotion: %s" % (emotions[0] if emotions else "default"),
        "---",
        "…",
        "```",
        "",
    ]


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


def install_personality(slug, persona_text, hermes_home):
    """Insert agent.personalities.<key> into config.yaml, preserving the file."""
    key = personality_key(slug)
    config = hermes_home / "config.yaml"
    entry = "    %s: %s\n" % (key, yaml_block_scalar(persona_text.rstrip(), 6))

    if not config.exists():
        warn("%s not found — paste the generated .personality.yaml manually" % config)
        return False
    text = config.read_text(encoding="utf-8")
    if re.search(r"^    %s:" % re.escape(key), text, re.M):
        warn("personality %r already exists in %s; not touching it "
             "(remove it first to re-import)" % (key, config))
        return False

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


def import_charx(charx_path, assets_dir, personas_dir, force, install, hermes_home):
    zf, data = load_card(charx_path)
    name = data["name"].strip()
    slug = name.lower()
    log("importing %r (folder: portraits/%s)" % (name, slug))

    emotions = extract_assets(zf, data, slug, assets_dir, force)

    persona_text = build_persona(data, slug, emotions)
    personas_dir.mkdir(parents=True, exist_ok=True)
    persona_md = personas_dir / (slug + ".md")
    persona_md.write_text(persona_text, encoding="utf-8")
    log("  write  %s" % persona_md)
    snippet = personas_dir / (slug + ".personality.yaml")
    snippet.write_text(build_yaml_snippet(slug, persona_text), encoding="utf-8")
    log("  write  %s" % snippet)

    installed = install and install_personality(slug, persona_text, hermes_home)

    key = personality_key(slug)
    log("")
    log("done. next steps:")
    if not installed:
        log("  1. merge %s into ~/.hermes/config.yaml (under agent.personalities)" % snippet.name)
        step = 2
    else:
        step = 1
    log("  %d. make sure %s is the extension's asset dir served at "
        "/extensions/risu-display/assets/" % (step, assets_dir))
    log("  %d. in a Hermes session: /personality %s" % (step + 1, key))
    return slug, emotions


# ---------------------------------------------------------------- selftest --

def _make_charx(path, spec="chara_card_v3", name="Mira", assets=None, files=None):
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
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("card.json", json.dumps({"spec": spec, "spec_version": "3.0", "data": data}))
        for inner, blob in (files or {}).items():
            z.writestr(inner, blob)


def selftest():
    import tempfile
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        assets_dir, personas_dir = td / "assets", td / "personas"

        # 1. happy path: emotions + icon, Korean emotion name, duplicate name
        files = {"assets/emotion/joy.svg": svg, "assets/emotion/joy2.svg": svg,
                 "assets/icon/main.svg": svg}
        cx = td / "ok.charx"
        _make_charx(cx, files=files, assets=[
            {"type": "emotion", "uri": "embeded://assets/emotion/joy.svg", "name": "Joy", "ext": "svg"},
            {"type": "emotion", "uri": "embeded://assets/emotion/joy2.svg", "name": "joy", "ext": "svg"},
            {"type": "emotion", "uri": "embeded://assets/emotion/joy.svg", "name": "수줍음", "ext": "svg"},
            {"type": "emotion", "uri": "ccdefault:", "name": "ghost", "ext": "png"},
            {"type": "icon", "uri": "embeded://assets/icon/main.svg", "name": "main", "ext": "svg"},
        ], name="Star Chart Mira")
        slug, emotions = import_charx(cx, assets_dir, personas_dir, force=False,
                                      install=False, hermes_home=td)
        assert slug == "star chart mira", slug
        assert emotions == ["joy", "수줍음"], emotions
        pdir = assets_dir / "portraits" / slug
        assert (pdir / "joy.svg").exists() and (pdir / "수줍음.svg").exists()
        assert (pdir / "default.svg").exists()
        persona = (personas_dir / (slug + ".md")).read_text(encoding="utf-8")
        assert "{{char}}" not in persona and "{{user}}" not in persona
        assert "sextant" in persona and "dying star" in persona
        assert "joy, 수줍음" in persona
        assert "speaker: Star Chart Mira" in persona
        yml = (personas_dir / (slug + ".personality.yaml")).read_text(encoding="utf-8")
        assert "star-chart-mira: |" in yml

        # 2. emotions only, no icon -> default copied from first emotion
        cx2 = td / "noicon.charx"
        _make_charx(cx2, name="Noicon", files={"assets/emotion/sad.svg": svg},
                    assets=[{"type": "emotion", "uri": "embeded://assets/emotion/sad.svg",
                             "name": "sad", "ext": "svg"}])
        import_charx(cx2, assets_dir, personas_dir, False, False, td)
        assert (assets_dir / "portraits" / "noicon" / "default.svg").exists()

        # 3. config.yaml install merge
        cfg = td / "config.yaml"
        cfg.write_text("agent:\n  model: foo\n  personalities:\n"
                       "    helpful: \"Be helpful.\"\nother: 1\n", encoding="utf-8")
        assert install_personality("noicon", "Persona body\nline two", td)
        merged = cfg.read_text(encoding="utf-8")
        assert "    noicon: |" in merged and "helpful" in merged and "other: 1" in merged
        try:
            import yaml
            parsed = yaml.safe_load(merged)
            assert "Persona body" in parsed["agent"]["personalities"]["noicon"]
        except ImportError:
            pass
        # duplicate install refuses
        assert not install_personality("noicon", "x", td)

        # 4. v2 card rejected
        cx3 = td / "v2.charx"
        _make_charx(cx3, spec="chara_card_v2")
        try:
            import_charx(cx3, assets_dir, personas_dir, False, False, td)
        except SystemExit:
            pass
        else:
            raise AssertionError("v2 card was not rejected")

    print("selftest OK")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("charx", nargs="?", help="path to the .charx file")
    p.add_argument("--assets-dir", type=Path, default=REPO_ROOT / "assets",
                   help="risu-display assets dir (default: this repo's assets/)")
    p.add_argument("--personas-dir", type=Path, default=REPO_ROOT / "personas",
                   help="output dir for the generated persona (default: personas/)")
    p.add_argument("--hermes-home", type=Path, default=Path.home() / ".hermes",
                   help="Hermes home for --install (default: ~/.hermes)")
    p.add_argument("--install", action="store_true",
                   help="merge the personality into <hermes-home>/config.yaml")
    p.add_argument("--force", action="store_true", help="overwrite existing assets")
    p.add_argument("--selftest", action="store_true", help="run built-in tests")
    args = p.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.charx:
        p.error("charx file required (or --selftest)")
    import_charx(Path(args.charx), args.assets_dir, args.personas_dir,
                 args.force, args.install, args.hermes_home)


if __name__ == "__main__":
    main()
