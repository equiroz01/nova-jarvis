// face.js — NOVA Face visualizer toggle + lifecycle.
//
// The face is an ALTERNATIVE to the classic arc-reactor, not an extra widget.
// A single preference (localStorage 'nova-visual' = 'reactor' | 'face') swaps
// the avatar everywhere: hero panel (TEXT/VOICE), speaking overlay, and the
// hands-free HUD. Default is 'reactor', so an untouched NOVA looks exactly as
// before and pays zero cost (the heavy face assets load lazily on first enable).
//
// The face is "dumb": it only reacts to events the rest of the app already
// emits on the bus. We never reach into chat/voice/handsfree internals.
//   audio:started / audio:ended / audio:blocked  → speaking (via bindNovaToBus)
//   nova:thinking {on}                           → thinking
//   nova:listening {on}                          → listening / idle
//   hf:open / hf:close                           → relocate canvas to/from HUD

import { NovaFace } from '/static/face/src/nova-face.js';
import { bindNovaToBus } from '/static/face/web/nova-face-bind.js';
import bus from './eventbus.js';

const PREF_KEY = 'nova-visual';

let face = null;            // NovaFace instance (lazy)
let visual = 'reactor';     // 'reactor' | 'face'

function isFace() { return visual === 'face'; }

/** Create the face instance once, wire audio-driven lip-sync, then reuse. */
function ensureFace() {
  if (face) return face;
  face = new NovaFace({
    container: '#novaFace',
    assetBase: '/static/face/assets/',
  });
  bindNovaToBus(face, bus); // audio:started/ended/blocked → speaking + envelope
  return face;
}

function heroHost() { return document.getElementById('novaFace'); }
function hudHost() { return document.getElementById('hfFaceSlot'); }

/** Move the live canvas between the hero panel and the hands-free HUD. */
function relocate(toHud) {
  if (!face) return;
  const host = toHud ? hudHost() : heroHost();
  if (host && face.root.parentNode !== host) host.appendChild(face.root);
}

function applyVisual(mode) {
  visual = mode === 'face' ? 'face' : 'reactor';
  if (isFace()) {
    document.body.setAttribute('data-visual', 'face');
    ensureFace();
    relocate(false);   // start in the hero panel
    face.start();
  } else {
    document.body.removeAttribute('data-visual');
    if (face) { relocate(false); face.stop(); }
  }
  localStorage.setItem(PREF_KEY, visual);
}

function toggleVisual() {
  applyVisual(isFace() ? 'reactor' : 'face');
}

export function isFaceEnabled() { return isFace(); }

export function init() {
  // These handlers are always registered but no-op while the face is absent or
  // in reactor mode, so they cost nothing for the default experience.
  bus.on('nova:thinking', (d) => { if (face && isFace()) face.think(!!(d && d.on)); });
  bus.on('nova:listening', (d) => {
    if (!face || !isFace()) return;
    (d && d.on) ? face.listen() : face.idle();
  });

  // Hands-free opens a fullscreen HUD — bring the canvas along, then return it.
  bus.on('hf:open', () => { if (isFace()) relocate(true); });
  bus.on('hf:close', () => { if (isFace()) relocate(false); });

  const btn = document.getElementById('faceToggle');
  if (btn) btn.addEventListener('click', toggleVisual);

  applyVisual(localStorage.getItem(PREF_KEY) || 'reactor');
}
