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
      "files": ["manifest.json", "risu-display.js", "risu-display.css"]
    }
  }
}
```

Restart the WebUI server.

## Usage

Tell your AI agent to use these code block formats:

- ```` ```risu-portrait ```` — Character portrait with name and image
- ```` ```risu-status ```` — Status panel (HP, MP, mood, etc.)
- ```` ```risu-dialogue ```` — Character dialogue with name and text
- ```` ```risu-gallery ```` — Image gallery grid

## License

MIT
