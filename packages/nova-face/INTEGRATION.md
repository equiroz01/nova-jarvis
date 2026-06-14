# NOVA Face — Guía de integración para el core

Módulo: `packages/nova-face/`. Un solo core visual (`src/nova-face.js`) que se consume
desde la **web** y desde la **app móvil** (Expo/RN vía WebView). La cara es "tonta": la
controla la app con una API imperativa. **El core decide *cuándo* hablar/pensar/escuchar
y empuja la amplitud; la cara solo reacciona.**

## Contrato (lo único que hay que saber)

| Acción del core            | Llamada                          |
|----------------------------|----------------------------------|
| Cambiar emoción en reposo  | `face.setEmotion('happy')`       |
| Empezó a hablar (TTS)      | `face.setMode('speaking')`       |
| Amplitud de voz (lip-sync) | `face.setLevel(0..1)` (repetido) |
| Terminó de hablar          | `face.idle()`                    |
| Procesando / backend       | `face.think(true)` / `think(false)` |
| Micrófono abierto          | `face.setMode('listening')` + `setLevel` |

Emociones: `neutral, happy, love, cool, sad, angry, surprised, sleepy, dizzy`.
Modos: `idle, speaking, listening, thinking`.

Regla de oro: en `speaking`/`listening` hay que **empujar `setLevel()` en cada frame de
audio**; sin nivel, la cara no late. En `thinking` no hace falta nivel (es procedural).

---

## 1) Web (`backend/app/static/`)

**a. Servir el paquete como estático.** En el backend (FastAPI):

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static/face", StaticFiles(directory="packages/nova-face"), name="face")
```

**b. Contenedor en `index.html`** (un div con tamaño; el módulo pinta dentro):

```html
<div id="novaFace" style="width:100%;height:48vh"></div>
```

**c. Inicializar en `static/js/app.js`** (junto al resto de `init()`):

```js
import { NovaFace } from '/static/face/src/nova-face.js';
import bus from './eventbus.js';
import { bindNovaToBus } from '/static/face/web/nova-face-bind.js';

const face = new NovaFace({ container:'#novaFace', assetBase:'/static/face/assets/' });
const nova = bindNovaToBus(face, bus);   // engancha audio:started / audio:ended
window.nova = nova;                       // opcional, para que otros módulos lo usen
```

`bindNovaToBus` ya conecta lo que tu `audio.js` emite (`audio:started`, `audio:ended`,
`audio:blocked`) → la cara entra/sale de "speaking" sola.

**d. Dónde llamar a cada estado desde tus módulos actuales:**

- `chat.js` (al enviar la petición / mientras llega el stream):
  `nova.thinking(true)` al iniciar, `nova.thinking(false)` al recibir la respuesta.
- `voice.js` / `handsfree.js` (push-to-talk o VAD): `nova.listening(true)` al abrir el
  micrófono, `nova.listening(false)` al cerrar.
- Emoción según sentimiento de la respuesta: `nova.emotion('happy')`.

**e. Lip-sync REAL (recomendado, 1 línea).** En `audio.js`, dentro de `playAudio()`,
justo después de crear el elemento `currentAudio = new Audio(...)`:

```js
face.connectAudioElement(currentAudio);   // la cara calcula la amplitud de la voz real
```

Sin esa línea funciona igual pero con una envolvente sintética (boca/ojos animados sin
seguir la voz exacta).

---

## 2) Móvil (Expo / React Native, carpeta `mobile/`)

El WebView carga el **mismo** core desde tu backend; no se reescribe nada.

```bash
npx expo install react-native-webview
```

En `mobile/App.tsx` (o donde vaya el avatar):

```tsx
import { useRef } from 'react';
import { NovaFaceView, NovaFaceHandle } from '../packages/nova-face/mobile/NovaFaceView';

const faceRef = useRef<NovaFaceHandle>(null);

<NovaFaceView
  ref={faceRef}
  baseUrl="https://TU_BACKEND/static/face"   // mismo paquete servido por el backend
  style={{ flex: 1 }}
  onReady={() => faceRef.current?.setEmotion('neutral')}
/>
```

Control desde la lógica de voz/chat (idéntico al contrato):

```ts
faceRef.current?.think(true);            // procesando / backend
faceRef.current?.setMode('speaking');    // empezó el TTS
faceRef.current?.setLevel(level);        // empuja el metering de expo-audio (0..1)
faceRef.current?.idle();
```

> Lip-sync móvil: el audio se reproduce nativo con `expo-audio`. Toma su *metering*
> (dBFS), normalízalo a 0..1 y pásalo a `setLevel()` en cada tick. Ejemplo de
> normalización: `level = Math.max(0, Math.min(1, (db + 60) / 60))`.

Protocolo interno (por si se depura el puente):
- App → WebView: `{type:'nova', cmd:'setMode'|'setEmotion'|'setLevel'|'think'|'idle'|'status', value}`
- WebView → App: `{type:'nova', event:'ready'|'modechange'|'emotionchange'|'status', value}`

---

## Checklist de integración

- [ ] Backend monta `/static/face` → `packages/nova-face/`.
- [ ] Web: `<div id="novaFace">` + init en `app.js` + `bindNovaToBus`.
- [ ] Web: `nova.thinking()` en `chat.js`, `nova.listening()` en `voice/handsfree`.
- [ ] Web (opcional): `face.connectAudioElement(currentAudio)` en `audio.js` para voz real.
- [ ] Móvil: `expo install react-native-webview` + `<NovaFaceView baseUrl=…>`.
- [ ] Móvil: empujar `setLevel()` con el metering de `expo-audio`.

## Notas

- El módulo trae su propio DOM/CSS (HUD, partículas, scanlines). El core solo aporta el
  contenedor y los controles de la app.
- `face.destroy()` limpia listeners y rAF al desmontar.
- Respeta `prefers-reduced-motion` y pausa el render con la pestaña oculta.
- Assets pesados (PNG 1254²): en móvil se sirven desde el backend (no se empaquetan en
  el bundle). Considera cachearlos / servirlos por CDN.
```
