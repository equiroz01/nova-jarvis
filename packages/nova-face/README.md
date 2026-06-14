# @nova/face

Rostro animado de NOVA como **módulo reutilizable**. Un solo core (canvas + Web Audio,
sin dependencias, sin build) que se consume desde la **web** directamente y desde la
**app móvil (Expo / React Native)** vía WebView. La animación se controla con una API
imperativa y **la app empuja el nivel de audio** para el lip-sync.

```
packages/nova-face/
├── src/nova-face.js          # CORE — clase NovaFace (framework-agnostic)
├── web/
│   ├── nova-face-bind.js     # enganche a tu eventbus.js (audio:started/ended)
│   └── demo.html             # demo consumidor (playground completo)
├── mobile/
│   ├── webview-host.html     # página que corre el core dentro del WebView
│   └── NovaFaceView.tsx      # componente RN + puente postMessage
├── assets/                   # NOVA_*.png + nova_sample.m4a
└── package.json              # exports: ".", "./web/bind", "./mobile/NovaFaceView"
```

## API del core

```js
import { NovaFace } from '@nova/face';            // o ruta relativa al src

const face = new NovaFace({
  container: '#nova',          // selector o elemento
  assetBase: '/static/face/assets/',
  emotion: 'neutral',          // estado en reposo
  hud: true,                   // viñeta + scanlines + esquinas + estado
  particles: true,
});

face.setEmotion('happy');                 // neutral|happy|love|cool|sad|angry|surprised|sleepy|dizzy
face.setMode('speaking');                 // idle|speaking|listening|thinking
face.setLevel(0.6);                       // amplitud 0..1 (llamar repetido al hablar)
face.think(true);                         // animación de "procesando / backend"
face.idle();
face.on('ready',  () => {});
face.on('modechange', m => {});
face.destroy();

// Audio self-driven (opcional, si prefieres que el módulo calcule la amplitud):
face.connectAudioElement(audioEl);        // <audio> que reproduces
face.connectStream(micStream);            // micrófono
face.connectAnalyser(analyserNode);       // un AnalyserNode existente
face.disconnectAudio();
```

El módulo inyecta su propio DOM y CSS dentro del `container`, así que basta un `<div>`
vacío con tamaño. **No** trae panel de controles: eso lo pone la app.

## Web

1. Sirve el paquete como estático del backend, p.ej. monta `packages/nova-face` en
   `/static/face` (FastAPI: `app.mount("/static/face", StaticFiles(directory="packages/nova-face"))`).
2. En tu `app.js`:

```js
import { NovaFace } from '/static/face/src/nova-face.js';
import bus from './eventbus.js';
import { bindNovaToBus } from '/static/face/web/nova-face-bind.js';

const face = new NovaFace({ container:'#novaFace', assetBase:'/static/face/assets/' });
const nova = bindNovaToBus(face, bus);     // engancha audio:started/ended

// desde chat.js / handsfree.js:
nova.thinking(true);   // al lanzar la petición / consultar backend
nova.thinking(false);  // al recibir respuesta
nova.listening(true);  // micrófono abierto
```

`bindNovaToBus` usa una envolvente sintética por defecto (cero cambios en tu `audio.js`).
Para **amplitud real**, en `playAudio()` tras crear el `Audio`:
`face.connectAudioElement(currentAudio)`.

Prueba el playground: abre `/static/face/web/demo.html`.

## Móvil (Expo / React Native)

```bash
npx expo install react-native-webview
```

```tsx
import { useRef } from 'react';
import { NovaFaceView, NovaFaceHandle } from '@nova/face/mobile/NovaFaceView';

const faceRef = useRef<NovaFaceHandle>(null);

<NovaFaceView
  ref={faceRef}
  baseUrl="https://TU_BACKEND/static/face"   // sirve el mismo paquete
  emotion="neutral"
  style={{ flex: 1 }}
  onReady={() => faceRef.current?.setEmotion('happy')}
/>

// desde tu lógica de voz/chat:
faceRef.current?.think(true);
faceRef.current?.setMode('speaking');
faceRef.current?.setLevel(level);   // empuja el metering de expo-audio (0..1)
faceRef.current?.idle();
```

El WebView carga `mobile/webview-host.html` desde tu backend, que a su vez importa el
mismo `src/nova-face.js`. Un solo código visual para web y móvil.

## Protocolo postMessage (RN ↔ WebView)

App → WebView: `{ type:'nova', cmd:'setMode'|'setEmotion'|'setLevel'|'think'|'speak'|'listen'|'idle'|'status', value }`
WebView → App: `{ type:'nova', event:'ready'|'modechange'|'emotionchange'|'status', value }`

## Estados visuales

- **idle** → expresión de la emoción actual, respiración, parpadeo, anillo HUD tenue.
- **speaking / listening** → ojos que laten con el nivel + anillo reactivo al espectro.
- **thinking** → base estable + arcos de procesamiento girando, orbe de escaneo,
  3 puntos en secuencia y texto de estado rotando (Procesando / Consultando backend / …).
