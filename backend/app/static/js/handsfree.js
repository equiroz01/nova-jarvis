// handsfree.js — VAD, wake word NOVA, interrupt
// Bug fixes applied:
// - Do NOT auto-start without user gesture. Show HF UI but require click to activate mic.
// - Wake word detection sends /voice only ONCE — reuse the response, don't call twice.

import bus from './eventbus.js';
import { addMessage, hideWelcome } from './messages.js';
import { playAudioAsync, stopAudio } from './audio.js';
import { speakTextAsync } from './tts.js';
import { speakFiller } from './fillers.js';
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

const VAD_SILENCE_MS = 1500;
const VAD_MIN_SPEECH_MS = 300;
const VAD_RESUME_DELAY_MS = 1000;
const VAD_MARGIN = 25;
const VAD_CALIBRATION_MS = 3000;
const VAD_MIN_THRESHOLD = 25;
let hfSpeechStart = 0;
let hfNoiseFloor = 20;
let hfCalibrating = false;
let hfAwake = false;
const WAKE_WORD = 'nova';
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
      stopAudio();
      window.speechSynthesis.cancel();
      document.getElementById('speakingOverlay').classList.remove('active');

      hfUnmute();
      hfSpeechDetected = true;
      hfSpeechStart = Date.now();
      hfSamples = [];
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
      hfSpeechDetected = true;
      hfSpeechStart = now;
      hfSamples = [];
      setHfState('speech');
    }
  } else if (hfState === 'speech') {
    if (level > threshold) {
      hfSilenceStart = 0;
    } else {
      if (hfSilenceStart === 0) hfSilenceStart = now;
      if (now - hfSilenceStart > VAD_SILENCE_MS) {
        if (now - hfSpeechStart > VAD_MIN_SPEECH_MS) {
          hfSendAudio();
        } else {
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

  // If not awake, check for wake word — send /voice ONCE and reuse the response
  if (!hfAwake) {
    try {
      const form = new FormData();
      form.append('audio', wavBlob, 'recording.wav');
      form.append('session_id', sessionId);
      const r = await fetch(API + '/voice', { method: 'POST', body: form });
      const data = await r.json();
      const transcript = (data.transcript || '').toLowerCase();

      if (transcript.includes(WAKE_WORD)) {
        hfAwake = true;
        if (hudS) hudS.textContent = 'ACTIVE';
        console.log('Wake word detected:', transcript);

        // BUG FIX: Reuse the SAME response — do NOT call /voice again
        if (data.response) {
          hideWelcome();
          if (data.transcript) { addMessage(data.transcript, 'user'); if (hudT) hudT.textContent = '"' + data.transcript + '"'; }
          addMessage(data.response, 'jarvis');
          if (hudR) hudR.textContent = data.response.replace(/\*\*/g, '').substring(0, 200);

          setHfState('speaking');
          startInterruptMonitor();
          if (data.audio_base64) { await playAudioAsync(data.audio_base64, 'response'); }
          else { await speakTextAsync(data.response); }
        }
      } else {
        console.log('Not wake word, ignoring:', transcript);
      }
    } catch (e) {
      console.error('Wake check error:', e);
    }

    // Resume listening
    cancelAnimationFrame(_interruptRAF);
    if (hfActive && hfState !== 'speech') {
      await new Promise(r => setTimeout(r, VAD_RESUME_DELAY_MS));
      hfUnmute();
      setHfState('listening');
      if (!hfAwake && hudS) hudS.textContent = 'LISTENING -- say "NOVA"';
      hfVADLoop();
    }
    return;
  }

  // Already awake — process command normally
  hideWelcome();

  const filler = speakFiller('general');
  if (hudR) hudR.textContent = filler;

  const form = new FormData();
  form.append('audio', wavBlob, 'recording.wav');
  form.append('session_id', sessionId);

  try {
    const r = await fetch(API + '/voice', { method: 'POST', body: form });
    const data = await r.json();

    // Stop filler
    stopAudio('filler');

    if (!data.transcript && !data.response) {
      // No speech
    } else {
      if (data.transcript) {
        addMessage(data.transcript, 'user');
        if (hudT) hudT.textContent = '"' + data.transcript + '"';
      }
      if (data.response) {
        addMessage(data.response, 'jarvis');
        if (hudR) hudR.textContent = data.response.replace(/\*\*/g, '').substring(0, 200);
      }

      setHfState('speaking');
      startInterruptMonitor();

      if (data.audio_base64) {
        await playAudioAsync(data.audio_base64, 'response');
      } else if (data.response) {
        await speakTextAsync(data.response);
      }
    }
  } catch (e) {
    console.error('Voice error:', e);
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
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true }
    });
    hfContext = new AudioContext({ sampleRate: 16000 });
    hfSource = hfContext.createMediaStreamSource(hfStream);

    hfAnalyser = hfContext.createAnalyser();
    hfAnalyser.fftSize = 512;
    hfSource.connect(hfAnalyser);

    hfProcessor = hfContext.createScriptProcessor(4096, 1, 1);
    hfProcessor.onaudioprocess = (e) => {
      if (hfSpeechDetected) {
        hfSamples.push(new Float32Array(e.inputBuffer.getChannelData(0)));
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
    hfAwake = false;
    setHfState('listening');
    const hudS = document.getElementById('hfHudStatus');
    if (hudS) hudS.textContent = 'CALIBRATING...';
    calibrateNoiseFloor(() => {
      hfCalibrating = false;
      setHfState('listening');
      if (hudS) hudS.textContent = 'LISTENING -- say "NOVA"';
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
