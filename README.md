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

## License

MIT
