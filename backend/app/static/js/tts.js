// tts.js — Browser SpeechSynthesis

import { isTTSEnabled } from './theme.js';

function stripMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`(.+?)`/g, '$1')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/^#{1,3}\s+/gm, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^\d+[.)]\s+/gm, '')
    .replace(/\n+/g, '. ')
    .trim();
}

function detectLang(text) {
  const spanishPattern = /[áéíóúñ¿¡]|hola|noticias|aquí|tienes|puedes/i;
  return spanishPattern.test(text) ? 'es-ES' : 'en-US';
}

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices();
  const langPrefix = lang.slice(0, 2);
  return voices.find(v => v.lang.startsWith(langPrefix) && v.name.toLowerCase().includes('male'))
    || voices.find(v => v.lang.startsWith(langPrefix))
    || voices[0];
}

export function speakText(text) {
  if (!isTTSEnabled() || !('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();

  const clean = stripMarkdown(text);
  const overlay = document.getElementById('speakingOverlay');
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.lang = detectLang(clean);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;

  const preferred = pickVoice(utterance.lang);
  if (preferred) utterance.voice = preferred;

  utterance.onstart = () => { if (overlay) overlay.classList.add('active'); };
  utterance.onend = () => { if (overlay) overlay.classList.remove('active'); };
  utterance.onerror = () => { if (overlay) overlay.classList.remove('active'); };

  window.speechSynthesis.speak(utterance);
}

export function speakTextAsync(text) {
  if (!isTTSEnabled() || !('speechSynthesis' in window)) return Promise.resolve();
  return new Promise(resolve => {
    window.speechSynthesis.cancel();
    const clean = stripMarkdown(text);
    const overlay = document.getElementById('speakingOverlay');
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = detectLang(clean);
    utterance.rate = 1.05;

    const preferred = pickVoice(utterance.lang);
    if (preferred) utterance.voice = preferred;

    utterance.onstart = () => { if (overlay) overlay.classList.add('active'); };
    utterance.onend = () => { if (overlay) overlay.classList.remove('active'); resolve(); };
    utterance.onerror = () => { if (overlay) overlay.classList.remove('active'); resolve(); };

    window.speechSynthesis.speak(utterance);
  });
}

export function init() {
  // Voices already preloaded in theme.js
}
