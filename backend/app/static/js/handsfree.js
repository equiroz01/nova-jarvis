// handsfree.js — VAD, always-on voice, interrupt
// - No wake word needed — always listening when active
// - Do NOT auto-start without user gesture. Show HF UI but require click to activate mic.

import bus from './eventbus.js';
import { addMessage, hideWelcome } from './messages.js';
import { playAudio, playAudioAsync, stopAudio } from './audio.js';
import { speakTextAsync } from './tts.js';
import { speakFiller, speakInterrupt, startFillerLoop, stopFillerLoop, setFillerLoopType } from './fillers.js';
import { samplesToWav } from './voice.js';
import { setInputMode } from './chat.js';

let API;
let sessionId;

let hfStream = null;
let hfContext = null;
let hfAnalyser = null;
let hfSource = null;
let hfProcessor = null;
let hfSamples = [];
let hfActive = false;
let hfState = 'idle'; // idle, listening, speech, processing
let hfSilenceStart = 0;
let hfSpeechDetected = false;
let hfRAF = null;
let hfMuted = false;

const VAD_SILENCE_MS = 1200;      // 1.2s of silence to end utterance — snappier turns
const VAD_MIN_SPEECH_MS = 400;    // 400ms minimum speech to count (filters coughs/clicks)
const VAD_RESUME_DELAY_MS = 400;  // 0.4s after NOVA speaks before listening again
const VAD_MARGIN = 20;            // dB above noise floor to detect speech (was 25 — too high)
const VAD_CALIBRATION_MS = 3000;  // 3s noise floor calibration
const VAD_MIN_THRESHOLD = 20;     // absolute minimum threshold
// Pre-roll: keep the last ~768ms of audio at all times. When speech triggers,
// prepend it so the first word's onset isn't clipped (clipped onsets were the
// main cause of misrecognition — Whisper hallucinates on truncated words).
const PREROLL_CHUNKS = 3; // 3 × 4096 samples @ 16kHz ≈ 768ms
let hfPreroll = [];
let hfSpeechStart = 0;
let hfNoiseFloor = 20;
let hfCalibrating = false;
let hfAwake = true;  // Always awake — no wake word needed
let _interruptRAF = null;
const INTERRUPT_MARGIN = 12;

function setHfState(state) {
  hfState = state;
  const ring = document.getElementById('hfRing');
  const status = document.getElementById('hfStatus');
  const wf = document.getElementById('hfWaveform');
  const btn = document.getElementById('hfToggleBtn');
  const hud = document.getElementById('hfHud');
  const hudStatus = document.getElementById('hfHudStatus');
  if (ring) {
    ring.className = 'hf-ring';
    btn.className = 'mic-btn';
    status.className = 'voice-status';
  }

  if (state === 'listening') {
    if (ring) { ring.classList.add('listening'); btn.classList.add('recording'); status.textContent = 'LISTENING...'; wf.classList.add('active'); }
    if (hud) { hud.setAttribute('data-state', 'listening'); }
    if (hudStatus) { hudStatus.textContent = 'LISTENING'; }
    const t = document.getElementById('hfHudTranscript');
    if (t) t.textContent = '';
  } else if (state === 'speech') {
    if (ring) { ring.classList.add('speech'); btn.classList.add('recording'); status.textContent = 'HEARING YOU...'; status.classList.add('recording'); wf.classList.add('active'); }
    if (hud) { hud.setAttribute('data-state', 'speech'); }
    if (hudStatus) { hudStatus.textContent = 'HEARING YOU'; }
  } else if (state === 'processing') {
    if (ring) { ring.classList.add('processing'); btn.classList.add('processing'); status.textContent = 'PROCESSING...'; status.classList.add('processing'); wf.classList.remove('active'); }
    if (hud) { hud.setAttribute('data-state', 'processing'); }
    if (hudStatus) { hudStatus.textContent = 'PROCESSING'; }
  } else if (state === 'speaking') {
    if (hud) { hud.setAttribute('data-state', 'speaking'); }
    if (hudStatus) { hudStatus.textContent = 'SPEAKING'; }
  } else {
    if (wf) wf.classList.remove('active');
    if (status) status.textContent = 'PRESS TO ACTIVATE';
  }
}

function initHfWaveform() {
  const wf = document.getElementById('hfWaveform');
  if (wf && wf.children.length === 0) {
    for (let i = 0; i < 24; i++) {
      const bar = document.createElement('div');
      bar.className = 'waveform-bar';
      wf.appendChild(bar);
    }
  }
}

function calibrateNoiseFloor(callback) {
  if (!hfAnalyser) { callback(); return; }
  const samples = [];
  const start = Date.now();
  function measure() {
    if (Date.now() - start > VAD_CALIBRATION_MS) {
      if (samples.length > 0) {
        const avg = samples.reduce((a, b) => a + b, 0) / samples.length;
        hfNoiseFloor = Math.max(VAD_MIN_THRESHOLD, avg);
      }
      console.log('Noise floor calibrated:', hfNoiseFloor.toFixed(1), '| Threshold:', (hfNoiseFloor + VAD_MARGIN).toFixed(1));
      callback();
      return;
    }
    const data = new Uint8Array(hfAnalyser.frequencyBinCount);
    hfAnalyser.getByteFrequencyData(data);
    const level = data.reduce((a, b) => a + b, 0) / data.length;
    samples.push(level);
    requestAnimationFrame(measure);
  }
  measure();
}

function updateNoiseFloor(level) {
  if (hfState === 'listening' && !hfSpeechDetected) {
    hfNoiseFloor = hfNoiseFloor * 0.95 + level * 0.05;
    hfNoiseFloor = Math.max(VAD_MIN_THRESHOLD, hfNoiseFloor);
  }
}

function hfMute() {
  hfMuted = true;
  cancelAnimationFrame(hfRAF);
  if (hfProcessor && hfSource) {
    try { hfSource.disconnect(hfProcessor); } catch(e) {}
  }
}

function hfUnmute() {
  hfMuted = false;
  hfSamples = [];
  hfPreroll = [];
  hfSpeechDetected = false;
  hfSilenceStart = 0;
  cancelAnimationFrame(_interruptRAF);
  if (hfProcessor && hfSource) {
    try { hfSource.connect(hfProcessor); } catch(e) {}
  }
}

function startInterruptMonitor() {
  if (!hfAnalyser || !hfActive) return;
  function check() {
    if (!hfActive || hfState !== 'speaking') return;
    const data = new Uint8Array(hfAnalyser.frequencyBinCount);
    hfAnalyser.getByteFrequencyData(data);
    const level = data.reduce((a, b) => a + b, 0) / data.length;

    if (level > hfNoiseFloor + INTERRUPT_MARGIN) {
      interruptHF();
      window.speechSynthesis.cancel();
      document.getElementById('speakingOverlay').classList.remove('active');

      // Play acknowledgment: "Sí jefe, dígame"
      speakInterrupt();

      hfUnmute();
      hfSpeechDetected = true;
      hfSpeechStart = Date.now();
      hfSamples = hfPreroll.slice();
      hfPreroll = [];
      setHfState('speech');
      hfVADLoop();
      return;
    }
    _interruptRAF = requestAnimationFrame(check);
  }
  check();
}

function hfVADLoop() {
  if (!hfActive || !hfAnalyser || hfMuted) return;

  const data = new Uint8Array(hfAnalyser.frequencyBinCount);
  hfAnalyser.getByteFrequencyData(data);
  const level = data.reduce((a, b) => a + b, 0) / data.length;

  const threshold = hfNoiseFloor + VAD_MARGIN;
  updateNoiseFloor(level);

  // Update waveform
  const bars = document.getElementById('hfWaveform').querySelectorAll('.waveform-bar');
  if (bars.length) {
    const subset = new Uint8Array(hfAnalyser.frequencyBinCount);
    hfAnalyser.getByteFrequencyData(subset);
    bars.forEach((b, i) => {
      b.style.height = Math.max(4, (subset[i] || 0) / 255 * 28) + 'px';
    });
  }

  const now = Date.now();

  if (hfState === 'listening') {
    if (level > threshold) {
      console.log(`[VAD] Speech detected: level=${level.toFixed(0)} > threshold=${threshold.toFixed(0)}`);
      clearHudText(); // Fade out previous conversation
      hfSpeechDetected = true;
      hfSpeechStart = now;
      hfSamples = hfPreroll.slice(); // prepend pre-roll so word onset isn't clipped
      hfPreroll = [];
      setHfState('speech');
    }
  } else if (hfState === 'speech') {
    if (level > threshold) {
      hfSilenceStart = 0;
    } else {
      if (hfSilenceStart === 0) hfSilenceStart = now;
      const silenceElapsed = now - hfSilenceStart;
      if (silenceElapsed > VAD_SILENCE_MS) {
        const speechDuration = now - hfSpeechStart;
        console.log(`[VAD] Utterance complete: ${(speechDuration/1000).toFixed(1)}s speech, sending to backend`);
        if (speechDuration > VAD_MIN_SPEECH_MS) {
          hfSendAudio();
        } else {
          console.log(`[VAD] Too short (${speechDuration}ms), discarding`);
          hfSamples = [];
          hfSpeechDetected = false;
          hfSilenceStart = 0;
          setHfState('listening');
        }
        return;
      }
    }
  }

  hfRAF = requestAnimationFrame(hfVADLoop);
}

async function hfSendAudio() {
  setHfState('processing');
  hfSpeechDetected = false;
  hfSilenceStart = 0;
  hfMute();

  const wavBlob = samplesToWav(hfSamples, hfContext ? hfContext.sampleRate : 16000);
  hfSamples = [];
  const hudR = document.getElementById('hfHudResponse');
  const hudT = document.getElementById('hfHudTranscript');
  const hudS = document.getElementById('hfHudStatus');

  // Process command directly — no wake word needed
  hideWelcome();

  // Initial filler covers STT time; follow-up loop covers long agent calls.
  speakFiller('general');
  startFillerLoop('general');

  const form = new FormData();
  form.append('audio', wavBlob, 'recording.wav');
  form.append('session_id', sessionId);
  form.append('tts', 'false'); // we re-synthesize per sentence via /tts/chunked

  try {
    const r = await fetch(API + '/voice/stream', { method: 'POST', body: form });
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    let finalData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        let event;
        try { event = JSON.parse(line); } catch (e) { continue; }

        if (event.type === 'transcript') {
          // STT done — show transcript, switch to a context-aware filler
          addMessage(event.transcript, 'user');
          if (hudT) hudT.textContent = '"' + event.transcript + '"';
          setFillerLoopType(event.query_type || 'general');
          if (event.filler_audio_base64) {
            playAudio(event.filler_audio_base64, 'filler');
            if (hudR) hudR.textContent = event.filler_text || '';
          }
        } else if (event.type === 'result') {
          finalData = event;
        } else if (event.type === 'error') {
          console.error('Voice stream error:', event.detail);
        }
      }
    }

    // Stop fillers before speaking the real response
    stopFillerLoop();
    stopAudio('filler');

    if (finalData && finalData.response) {
      addMessage(finalData.response, 'jarvis');
      setHfState('speaking');
      startInterruptMonitor();
      await playChunkedHF(finalData.response);
    }
  } catch (e) {
    console.error('Voice error:', e);
  } finally {
    stopFillerLoop();
    stopAudio('filler');
  }

  // Resume listening
  cancelAnimationFrame(_interruptRAF);
  if (hfActive && hfState !== 'speech') {
    await new Promise(r => setTimeout(r, VAD_RESUME_DELAY_MS));
    hfUnmute();
    setHfState('listening');
    hfVADLoop();
  }
}

async function startHandsfree() {
  if (hfActive) return;
  try {
    hfStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    hfContext = new AudioContext({ sampleRate: 16000 });
    hfSource = hfContext.createMediaStreamSource(hfStream);

    hfAnalyser = hfContext.createAnalyser();
    hfAnalyser.fftSize = 512;
    hfSource.connect(hfAnalyser);

    hfProcessor = hfContext.createScriptProcessor(4096, 1, 1);
    hfProcessor.onaudioprocess = (e) => {
      const data = new Float32Array(e.inputBuffer.getChannelData(0));
      if (hfSpeechDetected) {
        hfSamples.push(data);
      } else {
        // Rolling pre-roll buffer while idle
        hfPreroll.push(data);
        while (hfPreroll.length > PREROLL_CHUNKS) hfPreroll.shift();
      }
    };
    hfSource.connect(hfProcessor);
    hfProcessor.connect(hfContext.destination);

    hfActive = true;
    hfSamples = [];
    hfSpeechDetected = false;
    initHfWaveform();

    // Calibrate noise floor before listening
    hfCalibrating = true;
    setHfState('listening');
    const hudS = document.getElementById('hfHudStatus');
    if (hudS) hudS.textContent = 'CALIBRATING...';
    calibrateNoiseFloor(() => {
      hfCalibrating = false;
      setHfState('listening');
      if (hudS) hudS.textContent = 'LISTENING';
      hfVADLoop();
    });
  } catch (e) {
    console.error('Hands-free mic error:', e);
    addMessage('Microphone access denied. Allow mic access for hands-free mode.', 'jarvis');
    setInputMode('text');
  }
}

export function stopHandsfree() {
  hfActive = false;
  cancelAnimationFrame(hfRAF);
  cancelAnimationFrame(_interruptRAF);
  if (hfProcessor) { hfProcessor.disconnect(); hfProcessor = null; }
  if (hfSource) { hfSource.disconnect(); hfSource = null; }
  if (hfAnalyser) { hfAnalyser.disconnect(); hfAnalyser = null; }
  if (hfStream) { hfStream.getTracks().forEach(t => t.stop()); hfStream = null; }
  if (hfContext) { hfContext.close(); hfContext = null; }
  hfSamples = [];
  hfSpeechDetected = false;
  setHfState('idle');
}

let _hfTTSAbort = null;

function clearHudText() {
  const hudT = document.getElementById('hfHudTranscript');
  const hudR = document.getElementById('hfHudResponse');
  if (hudT) { hudT.classList.add('fade-out'); }
  if (hudR) { hudR.classList.add('fade-out'); }
  setTimeout(() => {
    if (hudT) { hudT.textContent = ''; hudT.classList.remove('fade-out'); }
    if (hudR) { hudR.textContent = ''; hudR.classList.remove('fade-out'); }
  }, 500);
}

function appendHudSentence(text) {
  const hudR = document.getElementById('hfHudResponse');
  if (!hudR) return;
  if (!text.trim()) return;

  // Split by newlines to handle bullet points
  const lines = text.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const div = document.createElement('div');
    div.className = 'hf-sentence';

    // Check if it's a bullet point
    const bulletMatch = trimmed.match(/^[-*•]\s+(.*)/);
    if (bulletMatch) {
      const bullet = document.createElement('span');
      bullet.className = 'hf-bullet';
      bullet.textContent = '▸ ';
      div.appendChild(bullet);
      appendRichText(div, bulletMatch[1]);
    } else {
      appendRichText(div, trimmed);
    }

    hudR.appendChild(div);
  }
  // Auto-scroll to bottom
  hudR.scrollTop = hudR.scrollHeight;
}

function appendRichText(container, text) {
  // Render **bold**, *italic*, `code` as DOM elements
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  for (const part of parts) {
    if (part.startsWith('**') && part.endsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      container.appendChild(strong);
    } else if (part.startsWith('*') && part.endsWith('*')) {
      const em = document.createElement('em');
      em.textContent = part.slice(1, -1);
      container.appendChild(em);
    } else if (part.startsWith('`') && part.endsWith('`')) {
      const code = document.createElement('code');
      code.textContent = part.slice(1, -1);
      code.style.cssText = 'color:var(--amber);font-family:Share Tech Mono,monospace;font-size:14px';
      container.appendChild(code);
    } else {
      container.appendChild(document.createTextNode(part));
    }
  }
}

async function playChunkedHF(text) {
  if (_hfTTSAbort) _hfTTSAbort.abort();
  _hfTTSAbort = new AbortController();
  const signal = _hfTTSAbort.signal;

  // Clear previous response
  const hudR = document.getElementById('hfHudResponse');
  if (hudR) hudR.textContent = '';

  try {
    const r = await fetch(API + '/tts/chunked', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal,
    });

    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';

    while (true) {
      if (signal.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim() || signal.aborted) continue;
        try {
          const chunk = JSON.parse(line);
          // Show sentence on HUD as it plays
          if (chunk.text) appendHudSentence(chunk.text);
          if (chunk.audio_base64) {
            await playAudioAsync(chunk.audio_base64, 'response');
          }
        } catch (e) { /* skip */ }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') console.warn('[hf] chunked TTS error:', e);
  }
}

function interruptHF() {
  if (_hfTTSAbort) _hfTTSAbort.abort();
  stopAudio();
}

function toggleHandsfree() {
  if (hfActive) {
    closeHfHud();
  } else {
    document.getElementById('hfHud').classList.add('active');
    document.getElementById('hfHudTranscript').textContent = '';
    document.getElementById('hfHudResponse').textContent = '';
    // BUG FIX: require user click (gesture) to start mic — this IS the gesture
    startHandsfree();
  }
}

function closeHfHud() {
  stopHandsfree();
  document.getElementById('hfHud').classList.remove('active');
  setInputMode('text');
}

export function init(config) {
  API = config.API;
  sessionId = config.sessionId;

  // BUG FIX: Do NOT auto-start. Show HF UI but require click to activate mic.
  // The old code had: setTimeout(() => setInputMode('handsfree'), 500)
  // We removed that. The user must click the HANDS-FREE tab or button.

  const hfToggleBtn = document.getElementById('hfToggleBtn');
  if (hfToggleBtn) hfToggleBtn.addEventListener('click', toggleHandsfree);

  const hfCloseBtn = document.querySelector('.hf-close');
  if (hfCloseBtn) hfCloseBtn.addEventListener('click', closeHfHud);
}
