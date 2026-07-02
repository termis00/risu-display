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
- ```` ```risu-gallery ```` — Image gallery grid
- ```` ```risu-scene ```` / ```` ```risu-panel ```` / ```` ```risu-image ```` — Scene images, info panels, single images

Emotion portraits resolve by convention from `assets/portraits/<character>/<emotion>.png|webp|jpg|svg`, falling back to the character's `default.*` and then `portraits/default.svg`.

See [SKILL.md](SKILL.md) for the full block syntax — it doubles as the instruction file for your agent.

## Importing a RisuAI character (.charx)

Export your character from RisuAI as `.charx`, then:

```bash
python3 tools/import_charx.py character.charx --install
```

This does three things:

1. Copies the card's emotion/icon assets into `assets/portraits/<character>/<emotion>.<ext>` (the convention risu-display resolves at render time).
2. Generates `personas/<character>.md` — the card's description, personality, scenario, lorebook, and greeting, plus rich-output rules listing the imported emotions — and a ready-to-merge `personas/<character>.personality.yaml`.
3. With `--install`, merges the persona into `~/.hermes/config.yaml` under `agent.personalities` (a `.bak` backup is kept; without `--install` it prints manual steps).

Then start a Hermes session and run `/personality <character>` — the agent role-plays the card and emits `risu-dialogue` blocks with matching emotions, which the extension renders with the imported portraits.

Options: `--assets-dir` (installed extension's asset dir), `--personas-dir`, `--hermes-home`, `--force` (overwrite existing assets). Remote (`http…`) asset URIs are not downloaded; `ccdefault:` entries are skipped. Only `chara_card_v3` cards are supported.

## License

MIT
