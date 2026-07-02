(() => {
  'use strict';
  if (window.__risuDisplayLoaded) return;
  window.__risuDisplayLoaded = true;

  const EXT_ID = 'risu-display';
  const ASSET_BASE = '/extensions/' + EXT_ID + '/';

  function getSetting(key, fallback) {
    try {
      const s = window.hermesExt.settings.forExtension(EXT_ID);
      const v = s.get(key);
      return v !== undefined && v !== null ? v : fallback;
    } catch (_) { return fallback; }
  }

  // --- Block content parser ---

  // Frontmatter ends at `---`, or at the first line that is not `key: value`
  // (so a missing `---` never swallows the body). `(?!\/\/)` keeps bare URLs
  // like `https://...` from being parsed as a `https:` prop.
  function parseBlock(raw) {
    const lines = raw.split('\n');
    const props = {};
    const entries = [];
    let bodyStart = -1;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line === '---') { bodyStart = i + 1; break; }
      if (!line) continue;
      const m = line.match(/^([a-zA-Z_]\w*)\s*:\s*(?!\/\/)(.+)$/);
      if (m) {
        props[m[1].toLowerCase()] = m[2].trim();
        entries.push({ key: m[1], value: m[2].trim() });
      } else {
        bodyStart = i;
        break;
      }
    }
    const body = bodyStart >= 0 ? lines.slice(bodyStart).join('\n').trim() : '';
    return { props, body, entries };
  }

  // Prop lines (original key case) minus reserved keys, for panel/status
  // blocks written without a `---` separator.
  function entryLines(entries, reserved) {
    return entries
      .filter(e => !reserved.includes(e.key.toLowerCase()))
      .map(e => e.key + ': ' + e.value)
      .join('\n');
  }

  const SIZES = ['small', 'medium', 'large', 'xlarge'];
  const PANEL_STYLES = ['dark', 'glass', 'minimal'];

  function pick(value, allowed, fallback) {
    value = (value || '').trim().toLowerCase();
    return allowed.includes(value) ? value : fallback;
  }

  function resolveImage(path) {
    if (!path) return '';
    if (/^https?:\/\//.test(path) || path.startsWith('/')) return path;
    return ASSET_BASE + 'assets/' + path;
  }

  function el(tag, cls, attrs) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === 'text') node.textContent = v;
        else node.setAttribute(k, v);
      }
    }
    return node;
  }

  function makeImg(src, alt, cls, fallbacks) {
    const img = el('img', cls || 'risu-image', { src: resolveImage(src), alt: alt || '', loading: 'lazy' });
    const queue = (fallbacks || []).slice();
    img.onerror = function() {
      if (queue.length) {
        this.src = resolveImage(queue.shift());
        return;
      }
      this.onerror = null;
      this.style.display = 'none';
      if (this.parentNode) {
        const fb = el('div', 'risu-image-fallback', { text: alt || src });
        this.parentNode.insertBefore(fb, this.nextSibling);
      }
    };
    return img;
  }

  // --- Emotion asset resolution ---
  // Convention: assets/portraits/<character>/<emotion>.<ext>, falling back to
  // the character's default portrait, then the shared default portrait.
  const EMOTION_EXTS = ['png', 'webp', 'jpg', 'gif', 'svg'];

  function emotionCandidates(character, emotion) {
    const c = encodeURIComponent(character.trim().toLowerCase());
    const e = encodeURIComponent((emotion || 'default').trim().toLowerCase());
    const paths = [];
    EMOTION_EXTS.forEach(ext => paths.push('portraits/' + c + '/' + e + '.' + ext));
    if (e !== 'default') {
      EMOTION_EXTS.forEach(ext => paths.push('portraits/' + c + '/default.' + ext));
    }
    paths.push('portraits/default.svg');
    return paths;
  }

  // Explicit image prop wins; otherwise emotion/character resolve by
  // convention. `auto` also resolves from the character name alone (used by
  // risu-portrait, where an image is always wanted); dialogue only resolves
  // when emotion/character is given, to avoid probing on every speech bubble.
  function resolvePortraitSource(props, character, auto) {
    const explicit = props.image || props.path || props.portrait || '';
    if (explicit) return { src: explicit, fallbacks: [] };
    const who = (props.character || character || '').trim();
    if (who && (auto || props.emotion || props.character)) {
      const candidates = emotionCandidates(who, props.emotion);
      return { src: candidates[0], fallbacks: candidates.slice(1) };
    }
    return { src: '', fallbacks: [] };
  }

  // --- Block processors ---

  function processImage(raw) {
    const { props, body } = parseBlock(raw);
    const path = props.path || body || raw.trim();
    const alt = props.alt || path.split('/').pop();
    const size = pick(props.size, SIZES, pick(getSetting('portrait_size', 'medium'), SIZES, 'medium'));
    const wrap = el('div', 'risu-image-wrap risu-size-' + size);
    wrap.appendChild(makeImg(path, alt));
    return wrap;
  }

  function processPortrait(raw) {
    const { props, body } = parseBlock(raw);
    if (!props.image && !props.path && body) props.image = body.split('\n')[0].trim();
    const name = props.name || '';
    const title = props.title || '';
    const size = pick(props.size, SIZES, pick(getSetting('portrait_size', 'medium'), SIZES, 'medium'));
    const { src, fallbacks } = resolvePortraitSource(props, name, true);

    const wrap = el('div', 'risu-portrait-wrap risu-size-' + size);
    wrap.appendChild(makeImg(src, name, 'risu-portrait-image', fallbacks));

    if (name || title) {
      const info = el('div', 'risu-portrait-info');
      if (name) info.appendChild(el('div', 'risu-portrait-name', { text: name }));
      if (title) info.appendChild(el('div', 'risu-portrait-title', { text: title }));
      wrap.appendChild(info);
    }
    return wrap;
  }

  function processPanel(raw) {
    const { props, body, entries } = parseBlock(raw);
    const title = props.title || '';
    const style = pick(props.style, PANEL_STYLES, pick(getSetting('panel_style', 'dark'), PANEL_STYLES, 'dark'));

    const wrap = el('div', 'risu-panel-wrap risu-panel-' + style);

    if (title) {
      wrap.appendChild(el('div', 'risu-panel-title', { text: title }));
    }

    const content = el('div', 'risu-panel-body');
    const textSource = [entryLines(entries, ['title', 'style']), body]
      .filter(Boolean).join('\n');

    textSource.split('\n').forEach(line => {
      const trimmed = line.trim();
      if (!trimmed) return;
      const sep = trimmed.indexOf(':');
      if (sep > 0 && sep < trimmed.length - 1) {
        const row = el('div', 'risu-panel-row');
        row.appendChild(el('span', 'risu-panel-label', { text: trimmed.slice(0, sep).trim() }));
        row.appendChild(el('span', 'risu-panel-value', { text: trimmed.slice(sep + 1).trim() }));
        content.appendChild(row);
      } else {
        content.appendChild(el('div', 'risu-panel-text', { text: trimmed }));
      }
    });

    wrap.appendChild(content);
    return wrap;
  }

  function processGallery(raw) {
    const height = getSetting('gallery_height', 'medium');
    const wrap = el('div', 'risu-gallery-wrap risu-gallery-' + height);

    raw.split('\n').forEach(line => {
      line.trim().split('|').forEach(path => {
        path = path.trim();
        if (!path) return;
        const item = el('div', 'risu-gallery-item');
        item.appendChild(makeImg(path, path.split('/').pop(), 'risu-gallery-image'));
        wrap.appendChild(item);
      });
    });
    return wrap;
  }

  function processDialogue(raw) {
    const { props, body } = parseBlock(raw);
    const speaker = props.speaker || props.name || '';
    const text = body || '';
    const { src, fallbacks } = resolvePortraitSource(props, speaker, false);

    const wrap = el('div', 'risu-dialogue-wrap');

    if (src) {
      wrap.appendChild(makeImg(src, speaker, 'risu-dialogue-portrait', fallbacks));
    }

    const bodyDiv = el('div', 'risu-dialogue-body');
    if (speaker) {
      bodyDiv.appendChild(el('div', 'risu-dialogue-speaker', { text: speaker }));
    }
    bodyDiv.appendChild(el('div', 'risu-dialogue-text', { text: text }));
    wrap.appendChild(bodyDiv);

    return wrap;
  }

  // Large centered emotion asset — RisuAI-style full illustration in the
  // message body, resolved from character + emotion like dialogue portraits.
  function processEmotion(raw) {
    const { props, body } = parseBlock(raw);
    const who = props.character || props.name || props.speaker || '';
    if (!props.emotion && body) props.emotion = body.split('\n')[0].trim();
    const size = pick(props.size, SIZES, 'xlarge');
    const { src, fallbacks } = resolvePortraitSource(props, who, true);
    if (!src) return null;

    const wrap = el('div', 'risu-image-wrap risu-emotion-wrap risu-size-' + size);
    wrap.appendChild(makeImg(src, (who ? who + ' — ' : '') + (props.emotion || 'default'),
                             'risu-image', fallbacks));
    return wrap;
  }

  function processScene(raw) {
    const { props, body } = parseBlock(raw);
    const image = props.image || props.path || body || raw.trim();
    const caption = props.caption || props.title || '';

    const wrap = el('div', 'risu-scene-wrap');
    wrap.appendChild(makeImg(image, caption, 'risu-scene-image'));

    if (caption) {
      wrap.appendChild(el('div', 'risu-scene-caption', { text: caption }));
    }
    return wrap;
  }

  function processStatus(raw) {
    const { props, body, entries } = parseBlock(raw);
    const title = props.title || '';

    const wrap = el('div', 'risu-status-wrap');
    if (title) {
      wrap.appendChild(el('div', 'risu-status-title', { text: title }));
    }

    const textSource = [entryLines(entries, ['title']), body].filter(Boolean).join('\n');
    const lines = textSource.split('\n').filter(l => l.trim());
    lines.forEach(line => {
      const m = line.match(/^(.+?):\s*([\d,]+)\s*\/\s*([\d,]+)\s*$/);
      if (m) {
        const cur = parseInt(m[2].replace(/,/g, ''), 10);
        const max = parseInt(m[3].replace(/,/g, ''), 10);
        const row = el('div', 'risu-status-bar-row');
        row.appendChild(el('span', 'risu-status-bar-label', { text: m[1].trim() }));
        const track = el('div', 'risu-status-bar-track');
        const pct = max > 0 ? Math.min(100, Math.max(0, (cur / max) * 100)) : 0;
        const fill = el('div', 'risu-status-bar-fill');
        fill.style.width = pct + '%';
        if (pct > 60) fill.classList.add('risu-bar-high');
        else if (pct > 30) fill.classList.add('risu-bar-mid');
        else fill.classList.add('risu-bar-low');
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(el('span', 'risu-status-bar-text', { text: m[2] + '/' + m[3] }));
        wrap.appendChild(row);
      } else {
        const sep = line.indexOf(':');
        if (sep > 0) {
          const row = el('div', 'risu-panel-row');
          row.appendChild(el('span', 'risu-panel-label', { text: line.slice(0, sep).trim() }));
          row.appendChild(el('span', 'risu-panel-value', { text: line.slice(sep + 1).trim() }));
          wrap.appendChild(row);
        }
      }
    });
    return wrap;
  }

  // --- Processor registry ---

  const PROCESSORS = {
    'language-risu-image': processImage,
    'language-risu-portrait': processPortrait,
    'language-risu-panel': processPanel,
    'language-risu-gallery': processGallery,
    'language-risu-dialogue': processDialogue,
    'language-risu-emotion': processEmotion,
    'language-risu-scene': processScene,
    'language-risu-status': processStatus,
  };

  function processRisuBlocks(container) {
    const root = container || document;
    for (const [langClass, processor] of Object.entries(PROCESSORS)) {
      root.querySelectorAll('code.' + langClass).forEach(codeEl => {
        const pre = codeEl.closest('pre');
        if (!pre || pre.dataset.risuProcessed) return;
        pre.dataset.risuProcessed = '1';

        try {
          const replacement = processor(codeEl.textContent);
          if (!replacement) return;

          const prev = pre.previousElementSibling;
          if (prev && prev.classList.contains('pre-header')) {
            prev.remove();
          }
          pre.replaceWith(replacement);
        } catch (e) {
          console.warn('[risu-display] Block processing failed:', e);
        }
      });
    }
  }

  // --- Keep "Processed" activity groups expanded ---
  // Hermes WebUI re-renders a finished turn's activity/worklog group collapsed.
  // For chat-style sessions that feels abrupt, so (setting keep_activity_open,
  // default on) auto-expand collapsed groups by clicking their summary button —
  // that path updates aria state and persists 'open' in the WebUI's own
  // disclosure store (hermes-activity-disclosure:<session>:<key>), so later
  // re-renders keep it open. Groups the user explicitly closed ('closed' in
  // the store) are left alone, and each DOM node is only auto-expanded once
  // so a manual collapse is never fought.
  const DISCLOSURE_PREFIX = 'hermes-activity-disclosure:';

  function userClosedGroup(key) {
    if (!key) return false;
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.indexOf(DISCLOSURE_PREFIX) === 0 && k.slice(-(key.length + 1)) === ':' + key) {
          return localStorage.getItem(k) === 'closed';
        }
      }
    } catch (_) { /* storage unavailable — treat as not closed */ }
    return false;
  }

  function expandActivityGroups() {
    if (getSetting('keep_activity_open', 'on') !== 'on') return;
    document.querySelectorAll(
      '.agent-activity-group.tool-call-group-collapsed,' +
      '.tool-call-group.tool-call-group-collapsed'
    ).forEach(group => {
      if (group.dataset.risuAutoExpanded) return;
      group.dataset.risuAutoExpanded = '1';
      const key = group.getAttribute('data-activity-disclosure-key') ||
                  group.getAttribute('data-tool-worklog-key') || '';
      if (userClosedGroup(key)) return;
      const summary = group.querySelector('.tool-call-group-summary, .tool-worklog-summary');
      if (summary && !summary.disabled && summary.getAttribute('aria-disabled') !== 'true') {
        summary.click();
      }
    });
  }

  let _expandQueued = false;

  function queueExpand() {
    if (_expandQueued) return;
    _expandQueued = true;
    requestAnimationFrame(() => {
      _expandQueued = false;
      try { expandActivityGroups(); } catch (e) {
        console.warn('[risu-display] activity expand failed:', e);
      }
    });
  }

  function watchActivityGroups() {
    queueExpand();
    new MutationObserver(queueExpand)
      .observe(document.body, { childList: true, subtree: true });
  }

  // --- Hook into postProcessRenderedMessages ---

  let _hookAttempts = 0;

  function hook() {
    if (typeof window.postProcessRenderedMessages === 'function') {
      const original = window.postProcessRenderedMessages;
      window.postProcessRenderedMessages = function(container) {
        original.call(this, container);
        processRisuBlocks(container);
      };
      // Catch messages that rendered before the hook was installed.
      processRisuBlocks(document);
      return;
    }
    if (++_hookAttempts > 20) {
      console.warn('[risu-display] postProcessRenderedMessages not found after retries');
      return;
    }
    setTimeout(hook, 250);
  }

  function start() {
    hook();
    watchActivityGroups();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
