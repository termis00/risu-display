# risu-display

RisuAI-style rich content rendering extension for [Hermes WebUI](https://github.com/nousresearch/hermes-webui).

Provides custom Markdown code block renderers for character portraits, status panels, dialogue, and galleries — inspired by RisuAI's display system.

## Installation

```bash
cd /path/to/hermes-webui/extensions
git clone https://github.com/termis00/risu-display.git
```

Then add to `extension-install-manifest.json`:

```json
{
  "version": 1,
  "installed": {
    "risu-display": {
      "version": "1.0.0",
      "files": ["manifest.json", "risu-display.js", "risu-display.css", "assets/**"]
    }
  }
}
```

Restart the WebUI server.

## Usage

Tell your AI agent to use these code block formats:

- ```` ```risu-portrait ```` — Character portrait with name and image
- ```` ```risu-status ```` — Status panel (HP, MP, mood, etc.)
- ```` ```risu-dialogue ```` — Character dialogue with name, text, and optional `emotion:` portrait
- ```` ```risu-emotion ```` — Large centered emotion illustration (RisuAI-style full-size asset)
- ```` ```risu-gallery ```` — Image gallery grid
- ```` ```risu-scene ```` / ```` ```risu-panel ```` / ```` ```risu-image ```` — Scene images, info panels, single images

Emotion portraits resolve by convention from `assets/portraits/<character>/<emotion>.png|webp|jpg|svg`, falling back to the character's `default.*` and then `portraits/default.svg`.

See [SKILL.md](SKILL.md) for the full block syntax — it doubles as the instruction file for your agent.

## Importing a RisuAI character (.charx)

Export your character from RisuAI as `.charx` (JPEG-wrapped CharX exports work too; PNG cards are not supported), then:

```bash
python3 tools/import_charx.py character.charx --install
```

This does three things:

1. Copies the card's assets into the risu-display layout: emotions to `assets/portraits/<character>/<emotion>.<ext>`, scene images to `assets/scenes/<character>/<tag>.<ext>`. RisuAI's `x-risu-asset` entries are classified using the card's **own tag lists** (the "Image Asset Protocol" lorebook entry); `CharName_` prefixes are stripped and declared extensions are corrected against the actual image bytes.
2. Generates `personas/<character>.md` — description, personality, scenario, lorebook, and greeting, plus rich-output rules listing the imported emotion/scene tags and the card's own asset-usage notes — and a ready-to-merge `personas/<character>.personality.yaml`. RisuAI toggle conditionals (`{{#if …toggle…}}`) are resolved to one branch (default: toggle on; pick with `--toggle name=0`).
3. With `--install`, merges the persona into `~/.hermes/config.yaml` under `agent.personalities` (a `.bak` backup is kept; `--reinstall` replaces an existing entry; without `--install` it prints manual steps).

Then start a Hermes session and run `/personality <character>` — the agent role-plays the card and emits `risu-emotion` blocks, which the extension renders as large centered illustrations from the imported assets.

Options: `--assets-dir` (installed extension's asset dir), `--personas-dir`, `--hermes-home`, `--toggle NAME=VALUE`, `--reinstall`, `--force` (overwrite existing assets). Remote (`http…`) asset URIs are not downloaded; `ccdefault:` entries and RisuAI modules (`module.risum`) are skipped. Only `chara_card_v3` cards are supported.

> Migration note: if you previously patched a copy of `import_charx.py` outside this repo, replace it with this version — it supersedes the ad-hoc `x-risu-asset` keyword classification and marker-based dedupe.

## License

MIT
