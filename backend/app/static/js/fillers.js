// fillers.js — Filler phrases, greeting, pre-cache

import { playAudio } from './audio.js';

let API;
let isFirstMessage = true;

const FILLER_BANK = {
  general: [
    "Un momento...", "Dejeme ver...", "Ya le digo, jefe...", "Permitame...",
    "Ehh, un segundo...", "Ya va...", "Dejeme pensar...", "A ver...",
    "Mmm, ya le respondo...", "Un segundito...", "Uy, buena pregunta...",
    "Ya le cuento...", "Listo, dejeme ver...", "Voy a revisar eso...",
    "Ay, ya voy...", "Que maravilla, ya le digo...", "Espereme un momentico...",
    "Ya casi, un segundo...", "Aja, dejeme mirar...", "Listo, ya voy por eso...",
  ],
  search: [
    "Estoy buscando en internet...", "Dejeme buscar eso...", "Ya reviso, un segundo...",
    "Consultando fuentes...", "Buscando informacion...", "Dejeme revisar en la web...",
    "Ya lo busco...", "Chequeando en internet...", "Ay, ya voy, dejeme buscar...",
    "Listo, ya estoy buscando...", "Uy, dejeme mirar eso...", "Ya le averiguo...",
  ],
  news: [
    "Revisando las noticias...", "Dejeme ver que hay de nuevo...",
    "Buscando las ultimas noticias...", "Revisando los titulares...",
    "A ver que paso hoy...", "Consultando las noticias...",
    "Uy, dejeme ver que hay...", "Ya miro que esta pasando...",
    "Voy a revisar las novedades...", "Que maravilla, ya le cuento que hay...",
  ],
  memory: [
    "Dejeme revisar mis notas...", "Un momento, reviso lo que se...",
    "Verificando en mi memoria...", "Dejeme buscar en mis registros...",
    "Ya reviso lo que tengo guardado...", "A ver, dejeme recordar...",
    "Un segundito, ya miro...", "Uy, eso lo tengo por aqui...",
  ],
  time: ["Ya verifico...", "Un segundo...", "Dejeme checar...", "Ya miro la hora..."],
  weather: ["Revisando el clima...", "Dejeme ver el pronostico...", "Consultando el tiempo...", "Ya miro como esta el clima..."],
};

const GREETINGS = {
  morning: [
    "Buenos dias, Mister Eme. A sus ordenes.",
    "Buenos dias, jefe. Sistemas en linea, listos para usted.",
    "Buenos dias, Senor Emeldo. En que le asisto hoy?",
    "Buen dia, Mister Eme. N.O.V.A. operativa y a su disposicion.",
    "Buenos dias, jefe. Ya revise las novedades. Cuando guste.",
    "Buenos dias. Cafe y datos listos, Mister Eme.",
    "Buenos dias, Senor Emeldo. El dia se ve productivo.",
  ],
  afternoon: [
    "Buenas tardes, Mister Eme. Que necesita?",
    "Buenas tardes, jefe. Aqui estoy, como siempre.",
    "Buenas tardes, Senor Emeldo. A la orden.",
    "Buenas tardes, Mister Eme. N.O.V.A. en linea.",
    "Buenas tardes, jefe. Digame en que le ayudo.",
    "Buenas tardes. Listo para lo que venga, Mister Eme.",
    "Buenas tardes, Senor Emeldo. Sistemas operativos.",
  ],
  evening: [
    "Buenas noches, Mister Eme. Aun en pie, como usted.",
    "Buenas noches, jefe. N.O.V.A. a su servicio.",
    "Buenas noches, Senor Emeldo. Algo pendiente?",
    "Buenas noches, Mister Eme. Aqui no descansamos.",
    "Buenas noches, jefe. Digame que necesita.",
    "Buenas noches. Usted trabaja tarde, yo tambien. En que le ayudo?",
    "Buenas noches, Mister Eme. Todo en orden por aqui.",
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
 * Speak a filler phrase. Returns the filler text displayed.
 * On first message, plays a greeting instead.
 */
export function speakFiller(queryHint) {
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
  const filler = pickFiller(queryHint);

  // Request pre-cached filler audio from backend
  fetch(API + '/filler', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query_type: qtype })
  }).then(r => r.json()).then(data => {
    if (data.audio_base64) playAudio(data.audio_base64, 'filler');
  }).catch(() => {});

  return filler;
}

export function init(config) {
  API = config.API;
  preloadGreeting();
}
