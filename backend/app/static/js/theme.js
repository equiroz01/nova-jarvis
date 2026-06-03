// theme.js — Theme toggle and TTS enabled state

const SUN_SVG = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
const MOON_SVG = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';

let ttsEnabled = localStorage.getItem('jarvis-tts') !== 'off';

export function isTTSEnabled() {
  return ttsEnabled;
}

function updateTTSIcon() {
  const el = document.getElementById('ttsIcon');
  if (el) el.style.opacity = ttsEnabled ? '1' : '0.3';
}

function toggleTTS() {
  ttsEnabled = !ttsEnabled;
  localStorage.setItem('jarvis-tts', ttsEnabled ? 'on' : 'off');
  if (!ttsEnabled) window.speechSynthesis.cancel();
  updateTTSIcon();
}

function setThemeIcon(theme) {
  const el = document.getElementById('themeIcon');
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
  const parser = new DOMParser();
  const svg = parser.parseFromString(
    '<svg xmlns="http://www.w3.org/2000/svg">' + (theme === 'light' ? MOON_SVG : SUN_SVG) + '</svg>',
    'image/svg+xml'
  );
  Array.from(svg.documentElement.childNodes).forEach(n => el.appendChild(document.importNode(n, true)));
}

function toggleTheme() {
  const html = document.documentElement;
  const isLight = html.getAttribute('data-theme') === 'light';
  if (isLight) { html.removeAttribute('data-theme'); } else { html.setAttribute('data-theme', 'light'); }
  const next = isLight ? 'dark' : 'light';
  localStorage.setItem('jarvis-theme', next);
  setThemeIcon(next);
}

export function init() {
  // Restore saved theme
  const saved = localStorage.getItem('jarvis-theme') || 'dark';
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
  setThemeIcon(saved);

  // Update TTS icon
  updateTTSIcon();

  // Preload voices
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();

  // Attach button listeners
  const ttsBtn = document.getElementById('ttsToggle');
  if (ttsBtn) ttsBtn.addEventListener('click', toggleTTS);

  const themeBtn = document.getElementById('themeToggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
}
