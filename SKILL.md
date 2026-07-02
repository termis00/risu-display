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

`---` separates frontmatter props from body. If no `---`, the entire content is treated as body (or `_value` prop).

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
Color-coded: green (>60%), yellow (30-60%), red (<30%).

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
