# NOVA Mobile (Expo)

Cliente nativo de N.O.V.A. para iOS y Android. Habla con el backend FastAPI
(que corre en el Mac Studio) a través de tu túnel/dominio público.

## Qué hace

- **Chat de texto** con respuesta en streaming (`/chat/stream`, SSE) — muestra
  frases de relleno mientras NOVA piensa y va escribiendo la respuesta token a token.
- **Voz push-to-talk**: mantén presionado el micrófono, suéltalo y se sube el audio
  a `/voice/stream` (NDJSON). Reproduce el filler contextual y luego la respuesta TTS.
- **Ajustes**: URL del backend + API key, guardados cifrados en `expo-secure-store`,
  con botón de "Probar conexión" contra `/health`.
- Sesión estable por instalación (UUID); el botón `＋` arranca una conversación nueva.

## Arquitectura

| Archivo | Rol |
|---|---|
| `src/settings.ts` | URL + API key en SecureStore; gestión de `session_id` |
| `src/api.ts` | Streaming vía `XMLHttpRequest` (RN no soporta body streaming en `fetch`); parsea SSE y NDJSON |
| `src/audioQueue.ts` | Cola de reproducción de MP3 base64 (filler + TTS) con `expo-audio` |
| `src/screens/ChatScreen.tsx` | UI de chat + grabación push-to-talk |
| `src/screens/SettingsScreen.tsx` | Configuración del backend |

El backend transcodifica el audio m4a/AAC de Expo a PCM16 para el fallback de
Google Speech (`backend/app/services/stt.py::_decode_to_pcm16_mono_16k`). Whisper
local ya decodifica m4a nativamente.

## Desarrollo

```bash
cd mobile
npm install
npx expo start          # escanea el QR con Expo Go (chat funciona; la voz necesita dev build)
```

> La grabación de audio usa módulos nativos. En **Expo Go** el chat de texto
> funciona, pero para probar la voz necesitas un *development build* (abajo).

## Builds (EAS)

Requiere una cuenta Expo (gratis) y el CLI:

```bash
npm i -g eas-cli
eas login
eas build:configure        # crea el projectId la primera vez
```

Perfiles definidos en `eas.json`:

```bash
# Development build (módulos nativos + hot reload)
eas build --profile development --platform android
eas build --profile development --platform ios

# Preview — APK instalable directo (Android) / IPA ad-hoc (iOS)
eas build --profile preview --platform android
eas build --profile preview --platform ios

# Producción — AAB para Play Store / build para App Store
eas build --profile production --platform all
```

- **Android**: el perfil `preview` genera un **APK** que instalas directo en el teléfono.
- **iOS**: para instalar en un dispositivo físico necesitas cuenta Apple Developer
  ($99/año). Sin ella puedes correr en el simulador con el perfil `development`.

## Configuración en el primer arranque

1. Abre la app → ⚙︎ Ajustes.
2. **URL del backend**: tu túnel/dominio (ej. `https://nova.tudominio.com`).
3. **API Key**: el valor de `NOVA_API_KEY` del backend (requerido al entrar por túnel;
   se omite en LAN).
4. "Probar conexión" → debe responder `✓ Conectado`.
5. Guardar.
