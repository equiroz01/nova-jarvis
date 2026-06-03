// audio.js — ALL audio playback (single source of truth)
// Bug fixes applied:
// - .catch() on every play() call
// - playAudioAsync ALWAYS resolves (timeout + catch)
// - Check isTTSEnabled() before playing
// - Priority system: response stops filler, filler never stops response
// - speakingOverlay always cleaned up

import bus from './eventbus.js';
import { isTTSEnabled } from './theme.js';

let currentAudio = null;
let currentPriority = 'none'; // 'none' | 'filler' | 'response'

function cleanupOverlay() {
  const overlay = document.getElementById('speakingOverlay');
  if (overlay) overlay.classList.remove('active');
}

function b64ToBlob(b64) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: 'audio/mp3' });
}

/**
 * Stop current audio playback.
 * If onlyPriority is set, only stop if current priority matches.
 */
export function stopAudio(onlyPriority) {
  if (onlyPriority && currentPriority !== onlyPriority) return;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.onended = null;
    currentAudio.onerror = null;
    currentAudio = null;
  }
  currentPriority = 'none';
  cleanupOverlay();
  bus.emit('audio:ended');
}

/**
 * Play audio from base64 data. Fire-and-forget version.
 * priority: 'filler' or 'response'
 */
export function playAudio(b64, priority) {
  if (!isTTSEnabled()) return;

  priority = priority || 'response';

  // Filler cannot stop a response
  if (priority === 'filler' && currentPriority === 'response') return;

  // Response always stops filler
  if (priority === 'response' && currentPriority === 'filler') {
    stopAudio();
  }

  // Stop any existing same-or-lower priority
  if (currentAudio) {
    stopAudio();
  }

  const overlay = document.getElementById('speakingOverlay');
  const blob = b64ToBlob(b64);
  const url = URL.createObjectURL(blob);
  currentAudio = new Audio(url);
  currentPriority = priority;

  if (overlay) overlay.classList.add('active');
  bus.emit('audio:started', { priority });

  currentAudio.onended = () => {
    cleanupOverlay();
    URL.revokeObjectURL(url);
    currentAudio = null;
    currentPriority = 'none';
    bus.emit('audio:ended');
  };
  currentAudio.onerror = () => {
    cleanupOverlay();
    URL.revokeObjectURL(url);
    currentAudio = null;
    currentPriority = 'none';
    bus.emit('audio:ended');
  };

  currentAudio.play().catch((err) => {
    console.warn('[audio] play() blocked:', err.message);
    cleanupOverlay();
    currentAudio = null;
    currentPriority = 'none';
    bus.emit('audio:blocked');
    bus.emit('audio:ended');
  });
}

/**
 * Play audio and return a promise that ALWAYS resolves.
 * Resolves when audio ends, errors, or after a 60s safety timeout.
 */
export function playAudioAsync(b64, priority) {
  if (!isTTSEnabled()) return Promise.resolve();

  priority = priority || 'response';

  // Filler cannot stop a response
  if (priority === 'filler' && currentPriority === 'response') return Promise.resolve();

  // Response always stops filler
  if (priority === 'response' && currentPriority === 'filler') {
    stopAudio();
  }

  if (currentAudio) {
    stopAudio();
  }

  return new Promise(resolve => {
    const overlay = document.getElementById('speakingOverlay');
    const blob = b64ToBlob(b64);
    const url = URL.createObjectURL(blob);
    currentAudio = new Audio(url);
    currentPriority = priority;

    // Safety timeout — ALWAYS resolve
    const safetyTimer = setTimeout(() => {
      console.warn('[audio] safety timeout reached, forcing resolve');
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.onended = null;
        currentAudio.onerror = null;
        currentAudio = null;
      }
      currentPriority = 'none';
      cleanupOverlay();
      URL.revokeObjectURL(url);
      bus.emit('audio:ended');
      resolve();
    }, 60000);

    function done() {
      clearTimeout(safetyTimer);
      cleanupOverlay();
      URL.revokeObjectURL(url);
      currentAudio = null;
      currentPriority = 'none';
      bus.emit('audio:ended');
      resolve();
    }

    if (overlay) overlay.classList.add('active');
    bus.emit('audio:started', { priority });

    currentAudio.onended = done;
    currentAudio.onerror = done;

    currentAudio.play().catch((err) => {
      console.warn('[audio] play() blocked:', err.message);
      clearTimeout(safetyTimer);
      cleanupOverlay();
      currentAudio = null;
      currentPriority = 'none';
      bus.emit('audio:blocked');
      bus.emit('audio:ended');
      resolve();
    });
  });
}

export function isPlaying() {
  return currentAudio !== null;
}

export function getCurrentPriority() {
  return currentPriority;
}

export function init() {
  // Listen for bus events
  bus.on('audio:play', (data) => {
    if (data && data.b64) {
      playAudio(data.b64, data.priority || 'response');
    }
  });
  bus.on('audio:stop', () => {
    stopAudio();
  });
}
