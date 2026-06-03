// markdown.js — Safe DOM-based markdown renderer (no innerHTML)

function appendInline(el, text) {
  const pattern = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(`(.+?)`)|(\[(.+?)\]\((.+?)\))/g;
  let lastIdx = 0, m;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > lastIdx) el.appendChild(document.createTextNode(text.slice(lastIdx, m.index)));
    if (m[1]) { const s = document.createElement('strong'); s.textContent = m[2]; el.appendChild(s); }
    else if (m[3]) { const em = document.createElement('em'); em.textContent = m[4]; el.appendChild(em); }
    else if (m[5]) { const c = document.createElement('code'); c.textContent = m[6]; el.appendChild(c); }
    else if (m[7]) { const a = document.createElement('a'); a.textContent = m[8]; a.href = m[9]; a.target = '_blank'; a.rel = 'noopener'; el.appendChild(a); }
    lastIdx = pattern.lastIndex;
  }
  if (lastIdx < text.length) el.appendChild(document.createTextNode(text.slice(lastIdx)));
}

export function renderMarkdown(text) {
  const container = document.createElement('div');
  container.className = 'msg-content';
  const lines = text.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') { i++; continue; }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (headingMatch) {
      const h = document.createElement('h' + headingMatch[1].length);
      appendInline(h, headingMatch[2]);
      container.appendChild(h); i++; continue;
    }
    if (/^[-*_]{3,}\s*$/.test(line.trim())) {
      container.appendChild(document.createElement('hr')); i++; continue;
    }
    if (/^\s*[-*+]\s/.test(line)) {
      const ul = document.createElement('ul');
      while (i < lines.length && /^\s*[-*+]\s/.test(lines[i])) {
        const li = document.createElement('li');
        appendInline(li, lines[i].replace(/^\s*[-*+]\s+/, ''));
        ul.appendChild(li); i++;
      }
      container.appendChild(ul); continue;
    }
    if (/^\s*\d+[.)]\s/.test(line)) {
      const ol = document.createElement('ol');
      while (i < lines.length && /^\s*\d+[.)]\s/.test(lines[i])) {
        const li = document.createElement('li');
        appendInline(li, lines[i].replace(/^\s*\d+[.)]\s+/, ''));
        ol.appendChild(li); i++;
      }
      container.appendChild(ol); continue;
    }
    if (line.trim().startsWith('```')) {
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      i++; const codeLines = [];
      while (i < lines.length && !lines[i].trim().startsWith('```')) { codeLines.push(lines[i]); i++; }
      code.textContent = codeLines.join('\n');
      pre.appendChild(code); container.appendChild(pre); i++; continue;
    }
    if (line.trim().startsWith('>')) {
      const bq = document.createElement('blockquote');
      const p = document.createElement('p');
      appendInline(p, line.replace(/^>\s*/, ''));
      bq.appendChild(p); container.appendChild(bq); i++; continue;
    }
    const p = document.createElement('p');
    appendInline(p, line);
    container.appendChild(p); i++;
  }
  return container;
}

export function init() {
  // No initialization needed — renderMarkdown is a pure utility
}
