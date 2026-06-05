// chat.js — Text input, streaming, input mode switching

import { addMessage, addStreamMessage, updateStreamMessage, hideWelcome, hideTyping } from './messages.js';
import { playAudio, playAudioAsync, stopAudio } from './audio.js';
import { speakFiller } from './fillers.js';
import { stopRecording, getIsRecording } from './voice.js';
import { stopHandsfree } from './handsfree.js';

let API;
let sessionId;
let inputMode = 'text';

export function getInputMode() { return inputMode; }

export function setInputMode(mode) {
  // Stop previous mode
  if (inputMode === 'handsfree') stopHandsfree();
  if (inputMode === 'voice' && getIsRecording()) stopRecording();

  inputMode = mode;
  document.querySelectorAll('.input-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.mode === mode));
  document.getElementById('voiceBar').classList.toggle('hidden', mode !== 'voice');
  document.getElementById('handsfreeBar').classList.toggle('hidden', mode !== 'handsfree');
  document.getElementById('textBar').style.display = mode === 'text' ? 'flex' : 'none';
  if (mode === 'text') document.getElementById('textInput').focus();
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function handleTextKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); }
  else { interruptTTS(); } // User typing = interrupt NOVA
  autoResize(e.target);
}

async function sendText() {
  const input = document.getElementById('textInput');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = ''; input.style.height = 'auto';
  hideWelcome();
  addMessage(msg, 'user');

  // PARALLEL: Fire filler + LLM at the same time
  const fillerText = speakFiller(msg);
  const streamBubble = addStreamMessage();
  updateStreamMessage(streamBubble, fillerText);

  try {
    const r = await fetch(API + '/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, session_id: sessionId })
    });

    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let fullResponse = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));

          if (data.type === 'filler') continue;

          if (data.type === 'token') {
            fullResponse += data.content;
            updateStreamMessage(streamBubble, fullResponse);
          }

          if (data.type === 'done') {
            fullResponse = data.response;
            updateStreamMessage(streamBubble, fullResponse);

            // Stop filler, play response sentence by sentence
            stopAudio('filler');
            playChunkedTTS(fullResponse);
          }

          if (data.type === 'error') {
            updateStreamMessage(streamBubble, data.detail);
          }
        } catch (e) { /* skip malformed lines */ }
      }
    }
  } catch (e) {
    hideTyping();
    addMessage('Connection error. Backend may be offline.', 'jarvis');
  }
}

let _ttsAbort = null; // AbortController for chunked TTS — allows interruption

async function playChunkedTTS(text) {
  // Abort any previous chunked TTS
  if (_ttsAbort) _ttsAbort.abort();
  _ttsAbort = new AbortController();
  const signal = _ttsAbort.signal;

  try {
    const r = await fetch(API + '/tts/chunked', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal,
    });

    // Read NDJSON stream — each line is a TTS chunk
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';

    while (true) {
      if (signal.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.trim()) continue;
        if (signal.aborted) break;
        try {
          const chunk = JSON.parse(line);
          if (chunk.audio_base64) {
            // Play this sentence and wait for it to finish before next
            await playAudioAsync(chunk.audio_base64, 'response');
          }
        } catch (e) { /* skip malformed lines */ }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') console.warn('[chat] chunked TTS error:', e);
  }
}

// Allow interrupting TTS from outside (e.g., user starts typing)
export function interruptTTS() {
  if (_ttsAbort) _ttsAbort.abort();
  stopAudio();
}

export function init(config) {
  API = config.API;
  sessionId = config.sessionId;

  // Input tabs
  document.querySelectorAll('.input-tab').forEach(tab => {
    tab.addEventListener('click', () => setInputMode(tab.dataset.mode));
  });

  // Text input
  const textInput = document.getElementById('textInput');
  if (textInput) textInput.addEventListener('keydown', handleTextKey);

  // Send button
  const sendBtn = document.getElementById('sendBtn');
  if (sendBtn) sendBtn.addEventListener('click', sendText);
}
