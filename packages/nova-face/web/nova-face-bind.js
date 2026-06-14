/**
 * nova-face-bind.js — engancha NovaFace al eventbus existente de la app web.
 *
 * Eventos que ya emite tu app (backend/app/static/js/audio.js):
 *   audio:started {priority}  audio:ended  audio:blocked
 *
 * Uso en app.js:
 *   import { NovaFace } from '/static/face/src/nova-face.js';
 *   import bus from './eventbus.js';
 *   import { bindNovaToBus } from '/static/face/web/nova-face-bind.js';
 *
 *   const face = new NovaFace({ container:'#novaFace', assetBase:'/static/face/assets/' });
 *   const nova = bindNovaToBus(face, bus);
 *
 *   // y desde chat.js / handsfree.js, cuando corresponda:
 *   nova.thinking(true);   // empezó a procesar / consultar backend
 *   nova.thinking(false);  // llegó la respuesta
 *   nova.listening(true);  // micrófono abierto (push-to-talk / VAD)
 *
 * Lip-sync: por defecto usa una envolvente sintética (cero cambios en tu audio.js).
 * Para amplitud REAL, ver la nota al final.
 */

export function bindNovaToBus(face, bus, opts = {}){
  const { speakEmotion = null } = opts;
  let envRAF = 0;

  function synthEnvelope(on){
    cancelAnimationFrame(envRAF);
    let phase = 0;
    const tick = () => {
      if (!on.v){ face.setLevel(face.S.level * 0.8); if (face.S.level < 0.02) return; envRAF = requestAnimationFrame(tick); return; }
      phase += 0.45;
      const base = 0.18 + 0.12*Math.sin(phase) + 0.08*Math.sin(phase*2.3);
      face.setLevel(Math.max(0.05, Math.min(1, base)));
      envRAF = requestAnimationFrame(tick);
    };
    tick();
  }
  const speaking = { v:false };

  bus.on('audio:started', () => {
    if (speakEmotion) face.setEmotion(speakEmotion);
    face.speak(); speaking.v = true; synthEnvelope(speaking);
  });
  const stop = () => { speaking.v = false; if (face.getMode()==='speaking') face.idle(); };
  bus.on('audio:ended', stop);
  bus.on('audio:blocked', stop);

  // API que el resto de la app llama directamente
  const api = {
    face,
    thinking(on = true){ face.think(on); },
    listening(on = true){ on ? face.listen() : face.idle(); },
    emotion(e){ face.setEmotion(e); },
    /** Conecta amplitud real desde un <audio> que tú controlas. */
    attachAudioElement(el){ face.connectAudioElement(el); },
    /** Conecta el micrófono (devuelve Promise). */
    async listenMic(){ const s = await navigator.mediaDevices.getUserMedia({audio:true}); face.connectStream(s); return s; },
  };
  return api;
}

export default bindNovaToBus;

/* -----------------------------------------------------------------------------
 * AMPLITUD REAL (opcional, 2 líneas en tu audio.js):
 *   import { NovaFace } from '...';   // o pásale la instancia
 *   en playAudio(), tras crear `currentAudio = new Audio(url)`:
 *       face.connectAudioElement(currentAudio);   // lip-sync con la voz real
 *   El módulo calcula la amplitud y mueve los ojos/anillo con la voz.
 * --------------------------------------------------------------------------- */
