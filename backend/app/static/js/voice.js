// voice.js — Push-to-talk recording, WAV encoding

import { addMessage, hideWelcome, hideTyping } from './messages.js';
import { playAudio, stopAudio } from './audio.js';
import { speakFiller, startFillerLoop, stopFillerLoop, setFillerLoopType } from './fillers.js';
import { startLiveWaveform, stopLiveWaveform } from './waveform.js';
import bus from './eventbus.js';

let API;
let sessionId;
let isRecording = false;
let audioContext = null;
let audioStream = null;
let audioSource = null;
let analyserNode = null;
let scriptProcessor = null;
let recordedSamples = [];

export function getAnalyser() { return analyserNode; }
export function getIsRecording() { return isRecording; }

function updateMicState(state) {
  const btn = document.getElementById('micBtn');
  const status = document.getElementById('voiceStatus');
  if (!btn || !status) return;
  btn.className = 'mic-btn';
  status.className = 'voice-status';
  if (state === 'recording') {
    btn.classList.add('recording'); status.classList.add('recording');
    status.textContent = 'RECORDING...';
  } else if (state === 'processing') {
    btn.classList.add('processing'); status.classList.add('processing');
    status.textContent = 'PROCESSING...';
  } else {
    status.textContent = 'PRESS TO SPEAK';
  }
}

export function samplesToWav(chunks, sampleRate) {
  let totalLength = 0;
  for (const c of chunks) totalLength += c.length;
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const c of chunks) { merged.set(c, offset); offset += c.length; }

  const int16 = new Int16Array(merged.length);
  for (let i = 0; i < merged.length; i++) {
    const s = Math.max(-1, Math.min(1, merged[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }

  const buffer = new ArrayBuffer(44 + int16.length * 2);
  const view = new DataView(buffer);
  function writeStr(off, str) { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); }
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + int16.length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);       // PCM
  view.setUint16(22, 1, true);       // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);      // 16-bit
  writeStr(36, 'data');
  view.setUint32(40, int16.length * 2, true);
  const int16View = new Int16Array(buffer, 44);
  int16View.set(int16);

  return new Blob([buffer], { type: 'audio/wav' });
}

async function startRecording() {
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true }
    });
    audioContext = new AudioContext({ sampleRate: 16000 });
    audioSource = audioContext.createMediaStreamSource(audioStream);

    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 64;
    audioSource.connect(analyserNode);

    scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    recordedSamples = [];
    scriptProcessor.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0);
      recordedSamples.push(new Float32Array(data));
    };
    audioSource.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);

    isRecording = true;
    updateMicState('recording');
    bus.emit('nova:listening', { on: true });
    startLiveWaveform(analyserNode);
  } catch (e) {
    console.error('Mic error:', e);
    addMessage('Microphone access denied. Please allow mic access in your browser.', 'jarvis');
  }
}

export function stopRecording() {
  isRecording = false;
  updateMicState('processing');
  bus.emit('nova:listening', { on: false });
  bus.emit('nova:thinking', { on: true });
  stopLiveWaveform();

  if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
  if (audioSource) { audioSource.disconnect(); audioSource = null; }
  if (analyserNode) { analyserNode.disconnect(); analyserNode = null; }
  if (audioStream) { audioStream.getTracks().forEach(t => t.stop()); audioStream = null; }

  const wavBlob = samplesToWav(recordedSamples, audioContext ? audioContext.sampleRate : 16000);
  if (audioContext) { audioContext.close(); audioContext = null; }
  recordedSamples = [];

  sendVoice(wavBlob);
}

function toggleRecording() {
  if (isRecording) { stopRecording(); return; }
  startRecording();
}

async function sendVoice(blob) {
  hideWelcome();

  // PARALLEL: filler plays while the backend processes; follow-up loop
  // covers long agent calls so there's never dead silence.
  speakFiller('general');
  startFillerLoop('general');

  const form = new FormData();
  form.append('audio', blob, 'recording.wav');
  form.append('session_id', sessionId);
  form.append('language', 'es');

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
          setFillerLoopType(event.query_type || 'general');
          if (event.filler_audio_base64) playAudio(event.filler_audio_base64, 'filler');
        } else if (event.type === 'result') {
          finalData = event;
        }
      }
    }

    stopFillerLoop();
    stopAudio('filler');
    bus.emit('nova:thinking', { on: false });
    if (finalData) {
      if (finalData.response) addMessage(finalData.response, 'jarvis');
      if (finalData.audio_base64) playAudio(finalData.audio_base64, 'response');
    }
    updateMicState('idle');
  } catch (e) {
    stopFillerLoop();
    stopAudio('filler');
    bus.emit('nova:thinking', { on: false });
    hideTyping();
    addMessage('Voice processing failed. Check backend.', 'jarvis');
    updateMicState('idle');
  }
}

export function init(config) {
  API = config.API;
  sessionId = config.sessionId;

  const micBtn = document.getElementById('micBtn');
  if (micBtn) micBtn.addEventListener('click', toggleRecording);
}
