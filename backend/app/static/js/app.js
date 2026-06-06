// app.js — Bootstrap: imports all modules and calls init() in the right order

import * as theme from './theme.js';
import * as health from './health.js';
import * as markdown from './markdown.js';
import * as messages from './messages.js';
import * as audio from './audio.js';
import * as tts from './tts.js';
import * as waveform from './waveform.js';
import * as fillers from './fillers.js';
import * as voice from './voice.js';
import * as chat from './chat.js';
import * as handsfree from './handsfree.js';
import * as tasks from './tasks.js';

const API = window.location.origin;
const sessionId = 'web-' + crypto.randomUUID().slice(0, 8);

const config = { API, sessionId };

// Display session ID
document.getElementById('sessionId').textContent = sessionId.toUpperCase();

// Initialize modules in dependency order
theme.init();                // theme + TTS toggle (no deps)
health.init(config);         // clock + health check
markdown.init();             // pure utility
messages.init();             // message display
audio.init();                // audio playback (event bus)
tts.init();                  // browser speech synthesis
waveform.init();             // arc reactor + waveform bars
fillers.init(config);        // filler phrases + greeting pre-cache
voice.init(config);          // push-to-talk recording
chat.init(config);           // text input + streaming
handsfree.init(config);      // VAD + always-on voice
tasks.init(config);          // background task badge + SSE
