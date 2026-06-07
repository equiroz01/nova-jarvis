// fillers.js — Filler phrases, greeting, pre-cache

import { playAudio } from './audio.js';

let API;
let isFirstMessage = true;

const FILLER_BANK = {
  general: [
    "Un momento, por favor...", "Déjeme ver...", "Ya le digo, jefe...", "Permítame...",
    "Ehh, un segundo...", "Ya va...", "Déjeme pensar...", "A ver, aquí voy...",
    "Mmm, ya le respondo...", "Un segundito, por favor...", "Uy, buena pregunta...",
    "Ya le cuento...", "Listo, déjeme ver...", "Voy a revisar eso...",
    "Ay, ya voy...", "Qué maravilla, ya le digo...", "Espéreme un momentico...",
    "Ya casi, un segundo...", "Ajá, déjeme mirar...", "Listo, ya voy por eso...",
  ],
  search: [
    "Estoy buscando en internet...", "Déjeme buscar eso...", "Ya reviso, un segundo...",
    "Consultando fuentes, por favor...", "Buscando información...", "Déjeme revisar en la web...",
    "Ya lo busco...", "Chequeando en internet...", "Ay, ya voy, déjeme buscar...",
    "Listo, ya estoy buscando...", "Uy, déjeme mirar eso...", "Ya le averiguo...",
  ],
  news: [
    "Revisando las noticias...", "Déjeme ver qué hay de nuevo...",
    "Buscando las últimas noticias...", "Revisando los titulares...",
    "A ver qué pasó hoy...", "Consultando las noticias...",
    "Uy, déjeme ver qué hay...", "Ya miro qué está pasando...",
    "Voy a revisar las novedades...", "Qué maravilla, ya le cuento qué hay...",
  ],
  memory: [
    "Déjeme revisar mis notas...", "Un momento, reviso lo que sé...",
    "Verificando en mi memoria...", "Déjeme buscar en mis registros...",
    "Ya reviso lo que tengo guardado...", "A ver, déjeme recordar...",
    "Un segundito, ya miro...", "Uy, eso lo tengo por aquí...",
  ],
  time: ["Ya verifico...", "Un segundo, por favor...", "Déjeme checar...", "Ya miro la hora..."],
  weather: ["Revisando el clima...", "Déjeme ver el pronóstico...", "Consultando el tiempo...", "Ya miro cómo está el clima..."],
  interrupt: [
    "Sí jefe, dígame.",
    "Claro, le escucho.",
    "Dígame, Señor Emeldo.",
    "Sí, a la orden.",
    "Entendido, ¿qué necesita?",
    "Sí, Mister Eme.",
    "Le escucho.",
    "Cómo no, dígame.",
    "Aquí estoy, ¿qué le digo?",
    "Sí señor, lo escucho.",
  ],
};

const GREETINGS = {
  morning: [
    "Buenos días, Mister Eme. A sus órdenes.",
    "Buenos días, jefe. Sistemas en línea, listos para usted.",
    "Buenos días, Señor Emeldo. ¿En qué le asisto hoy?",
    "Buen día, Mister Eme. NOVA operativa y a su disposición.",
    "Buenos días, jefe. Ya revisé las novedades. Cuando guste.",
    "Buenos días. Café y datos listos, Mister Eme.",
    "Buenos días, Señor Emeldo. El día se ve productivo.",
  ],
  afternoon: [
    "Buenas tardes, Mister Eme. ¿Qué necesita?",
    "Buenas tardes, jefe. Aquí estoy, como siempre.",
    "Buenas tardes, Señor Emeldo. A la orden.",
    "Buenas tardes, Mister Eme. NOVA en línea.",
    "Buenas tardes, jefe. Dígame en qué le ayudo.",
    "Buenas tardes. Listo para lo que venga, Mister Eme.",
    "Buenas tardes, Señor Emeldo. Sistemas operativos.",
  ],
  evening: [
    "Buenas noches, Mister Eme. Aún en pie, como usted.",
    "Buenas noches, jefe. NOVA a su servicio.",
    "Buenas noches, Señor Emeldo. ¿Algo pendiente?",
    "Buenas noches, Mister Eme. Aquí no descansamos.",
    "Buenas noches, jefe. Dígame qué necesita.",
    "Buenas noches. Usted trabaja tarde, yo también. ¿En qué le ayudo?",
    "Buenas noches, Mister Eme. Todo en orden por aquí.",
  ],
};

const _recentFillers = [];

function _getGreeting() {
  const h = new Date().getHours();
  const bank = h < 12 ? GREETINGS.morning : h < 18 ? GREETINGS.afternoon : GREETINGS.evening;
  return bank[Math.floor(Math.random() * bank.length)];
}

function pickFiller(msg) {
  const lower = (msg || '').toLowerCase();
  let cat = 'general';
  if (/noticias|news|novedades|titulares|pas[oó]|actualidad/.test(lower)) cat = 'news';
  else if (/busca|search|google|internet|encuentra|averigua/.test(lower)) cat = 'search';
  else if (/recuerdas|sabes|conoces|quien|quién|memoria/.test(lower)) cat = 'memory';
  else if (/hora|time|reloj/.test(lower)) cat = 'time';
  else if (/clima|weather|pron[oó]stico|temperatura|lluvia/.test(lower)) cat = 'weather';

  const bank = FILLER_BANK[cat] || FILLER_BANK.general;
  const available = bank.filter(f => !_recentFillers.includes(f));
  const pick = available.length ? available[Math.floor(Math.random() * available.length)] : bank[Math.floor(Math.random() * bank.length)];
  _recentFillers.push(pick);
  if (_recentFillers.length > 5) _recentFillers.shift();
  return pick;
}

function detectQueryType(msg) {
  const lower = (msg || '').toLowerCase();
  if (/noticias|news|novedades|titulares/.test(lower)) return 'news';
  if (/busca|search|internet/.test(lower)) return 'search';
  if (/recuerdas|sabes|conoces|memoria/.test(lower)) return 'memory';
  if (/hora|time/.test(lower)) return 'time';
  if (/clima|weather/.test(lower)) return 'weather';
  return 'general';
}

// Pre-cache greeting audio
let _greetingAudioB64 = null;
let _greetingText = null;

function preloadGreeting() {
  _greetingText = _getGreeting();
  fetch(API + '/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: _greetingText })
  }).then(r => r.json()).then(data => {
    if (data.audio_base64) _greetingAudioB64 = data.audio_base64;
  }).catch(() => {});
}

/**
 * Speak a filler phrase. Fetches text+audio from backend (single source of truth).
 * Returns a Promise that resolves with the filler text.
 * On first message, plays a greeting instead.
 */
export async function speakFiller(queryHint) {
  // First message of the session -> greeting (pre-cached audio)
  if (isFirstMessage) {
    isFirstMessage = false;
    const greeting = _greetingText || _getGreeting();
    if (_greetingAudioB64) {
      playAudio(_greetingAudioB64, 'filler');
    } else {
      fetch(API + '/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: greeting })
      }).then(r => r.json()).then(d => { if (d.audio_base64) playAudio(d.audio_base64, 'filler'); }).catch(() => {});
    }
    return greeting;
  }

  const qtype = detectQueryType(queryHint);

  // Single source: backend picks text + provides matching pre-cached audio
  try {
    const r = await fetch(API + '/filler', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query_type: qtype })
    });
    const data = await r.json();
    if (data.audio_base64) playAudio(data.audio_base64, 'filler');
    return data.text || pickFiller(queryHint);
  } catch (e) {
    // Fallback: use local text, no audio
    return pickFiller(queryHint);
  }
}

/**
 * Play an interrupt acknowledgment filler — "Sí jefe, dígame"
 * Uses pre-cached audio from backend for instant playback.
 */
export function speakInterrupt() {
  fetch(API + '/filler', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query_type: 'interrupt' })
  }).then(r => r.json()).then(data => {
    if (data.audio_base64) playAudio(data.audio_base64, 'response');
  }).catch(() => {});

  return pickFiller('interrupt');
}

export function init(config) {
  API = config.API;
  preloadGreeting();
}
