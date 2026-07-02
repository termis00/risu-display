---
name: risu-rich-content
description: Generate RisuAI-style rich content in assistant responses for Hermes WebUI using the risu-display extension (code-block-based rendering).
---

# Risu Rich Content — risu-display Extension

The user has the [risu-display](https://github.com/termis00/risu-display) extension installed in their Hermes WebUI. It renders fenced code blocks with special language tags as rich visual content (portraits, status bars, dialogue, galleries, etc.).

## Syntax: YAML-like frontmatter

````
```risu-<type>
key: value
key2: value2
---
body text
```
````

`---` separates frontmatter props from body. If `---` is omitted, frontmatter ends at the first line that is not `key: value` — everything from that line on is the body. Prefer writing the explicit `---`.

## Block Types

### risu-image — Single image
````
```risu-image
path: /api/file/raw?session_id=xxx&path=file.png
alt: description
size: medium
```
````
Sizes: `small` (80px), `medium` (150px), `large` (240px), `xlarge` (85% width, no border, centered).

### risu-portrait — Character portrait card
````
```risu-portrait
image: /api/file/raw?session_id=xxx&path=portrait.png
name: 캐릭터명
title: 직업 · 레벨
size: medium
```
````

### risu-panel — Info panel
````
```risu-panel
title: 캐릭터 정보
style: dark
---
HP: 85/100
MP: 42/80
레벨: 5
```
````
Styles: `dark` (default), `glass` (translucent), `minimal` (transparent).

### risu-gallery — Horizontal image gallery
````
```risu-gallery
/path/to/img1.png | /path/to/img2.png | /path/to/img3.png
```
````

### risu-dialogue — Speech bubble with portrait
````
```risu-dialogue
speaker: 캐릭터명
portrait: /path/to/portrait.png
---
대사 내용입니다.
```
````
Instead of an explicit `portrait:`, you can use `emotion:` (with the speaker as the character) — see "Emotion Portraits" below.

### risu-emotion — Large centered emotion asset
````
```risu-emotion
character: 캐릭터명
emotion: joy
```
````
Renders the character's emotion image big and centered in the message body (RisuAI-style full illustration), resolved the same way as emotion portraits (see "Emotion Portraits"). `size:` defaults to `xlarge`. Use this instead of `risu-dialogue` when the persona asks for large asset display; put the block in the middle of the message near the moment it depicts, and keep the dialogue itself as plain prose.

### risu-scene — Full-width scene image with caption
````
```risu-scene
image: /path/to/scene.png
caption: 배경 설명
```
````

### risu-status — HP/MP progress bars
````
```risu-status
title: 전투 스탯
---
HP: 85/100
MP: 42/80
STAMINA: 60/100
```
````
Color-coded: green (>60%), yellow (>30% and ≤60%), red (≤30%). Values may contain commas (`HP: 1,200/2,000`).

## Emotion Portraits

Portraits can be resolved automatically from a character + emotion instead of an explicit image path:

````
```risu-dialogue
speaker: Elara
emotion: joy
---
해냈어요! 유적의 봉인이 풀렸어요!
```
````

Resolution convention: `assets/portraits/<character>/<emotion>.png|webp|jpg|svg` (character and emotion are lowercased). If the emotion file is missing it falls back to the character's `default.*`, then to the shared `portraits/default.svg`.

- `risu-dialogue`: uses `speaker` as the character; add `emotion: <name>`. A `character:` prop overrides the folder name if it differs from the display name.
- `risu-portrait`: if no `image:` is given, resolves from `name` (+ optional `emotion:`) automatically.
- Common emotion names: `neutral`, `joy`, `sad`, `angry`, `surprised`, `embarrassed`, `thinking` — any name works as long as the asset file exists.
- Characters imported from RisuAI `.charx` cards (via `tools/import_charx.py`) install their emotion assets under this convention; the generated personality lists that character's exact available emotions — prefer that list.

## Usage Guidance (when to emit blocks)

To create a RisuAI-like experience, emit blocks consistently, not occasionally:

- **Character emotion display** — follow the style the active persona specifies. Compact style: `risu-dialogue` with `speaker` + `emotion` per speech. Large style (RisuAI-like, default for imported cards): one `risu-emotion` block per emotional beat in the middle of the message, dialogue as plain prose. Don't mix both in one message.
- **Scene or location change** → one `risu-scene` at the top of the message.
- **Stat changes** (HP/MP after combat, resource spend) → `risu-status` right after the event.
- **Inventory, quest info, loot** → `risu-panel`.
- **Introducing a character or a changed appearance** → `risu-portrait`.
- Multiple blocks per message are fine (e.g. scene → dialogue → status); interleave with normal prose.
- Emit each block complete and in one piece; don't split a block across messages.

## Image URL Resolution

- Absolute URLs (`https://...`) and absolute paths (`/...`) used as-is
- Relative paths resolved against `/extensions/risu-display/assets/`
- For chat attachments, use `/api/file/raw?session_id=<sid>&path=<filename>`

## Settings

| Key | Options | Default |
|---|---|---|
| `portrait_size` | small, medium, large | medium |
| `panel_style` | dark, glass, minimal | dark |
| `gallery_height` | small, medium, large | medium |
| `keep_activity_open` | on, off | on |

(`keep_activity_open` is user-facing UX, not agent-facing: it keeps the WebUI's "Processed" activity panel expanded after each turn.)
