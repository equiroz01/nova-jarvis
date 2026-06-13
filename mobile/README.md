# NOVA Mobile (Expo)

Cliente nativo de N.O.V.A. para iOS y Android. Habla con el backend FastAPI
(que corre en el Mac Studio) a través de tu túnel/dominio público.

Proyecto EAS: **[`@hypernovalabs/nova-mobile`](https://expo.dev/accounts/hypernovalabs/projects/nova-mobile)**
(org `hypernovalabs`, bundle `com.hypernovalabs.nova`). Ya está enlazado — el
`projectId` vive en `app.json` (`extra.eas.projectId`).

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

El proyecto ya está enlazado a expo.dev, así que **no** hace falta `eas init` /
`build:configure`. Solo necesitas el CLI y estar logueado en la cuenta correcta:

```bash
npm i -g eas-cli
eas login                  # usuario con acceso a la org `hypernovalabs`
eas whoami
```

Perfiles definidos en `eas.json` (`development` / `preview` / `production`):

```bash
# Preview — IPA ad-hoc (iOS) / APK instalable directo (Android)
eas build --profile preview --platform ios
eas build --profile preview --platform android

# Development build (módulos nativos + dev client)
eas build --profile development --platform ios

# Producción — build para App Store / AAB para Play Store
eas build --profile production --platform all
```

- **iOS (preview/production)**: requiere cuenta **Apple Developer** ($99/año; ya
  configurada: team *Hypernova Labs S.A.*). EAS genera el certificado de
  distribución y el provisioning ad-hoc automáticamente.
  - Para instalar en un iPhone físico hay que **registrar su UDID** una vez:
    ```bash
    eas device:create        # elige "Website" → abre el link/QR EN el iPhone e instala el perfil
    ```
    Luego el `eas build` incluye ese dispositivo en el provisioning. Para instalar,
    abre la página del build terminado **en el iPhone** y toca *Install* (OTA ad-hoc).
  - Sin dispositivo físico, usa el perfil `development` con `"ios": { "simulator": true }`.
- **Android**: el perfil `preview` genera un **APK** que instalas directo.

### Producción iOS (App Store / TestFlight)

El perfil `production` no tiene `distribution: internal`, así que EAS hace un build
de **distribución App Store** (no se instala directo: va a App Store Connect). El
`buildNumber` se autoincrementa solo (`appVersionSource: "remote"` + `autoIncrement`),
y `ITSAppUsesNonExemptEncryption: false` ya evita el prompt de export compliance.

```bash
eas build -p ios --profile production     # corre en modo interactivo la 1ª vez
```

La primera vez pide **login de Apple (2FA)** para crear las credenciales de store
(no se pueden generar en `--non-interactive`):
- **Distribution Certificate** → acepta el default (reutiliza el "Apple Distribution"
  del ad-hoc; el mismo cert sirve para ad-hoc y App Store).
- **App Store provisioning profile** → deja que EAS lo genere.

Subir el `.ipa` a App Store Connect → TestFlight:

```bash
eas submit -p ios --profile production
```

- Necesita un **app record en App Store Connect** para `com.hypernovalabs.nova`
  (créalo en appstoreconnect.apple.com, o deja que `eas submit` lo cree).
- Autenticación recomendada: **App Store Connect API key** (no expira con 2FA);
  configúrala en `eas.json` → `submit.production.ios` o deja que `eas submit` la pida.
- De TestFlight se envía a revisión de App Store desde la consola web.

### OTA updates (EAS Update)

`expo-updates` está configurado (canal `production`). Publicar JS sin recompilar:

```bash
eas update --branch production --message "..."
```

> Los OTA solo los reciben builds ya instalados con el mismo `runtimeVersion`
> (`app.json` → `runtimeVersion.policy = "appVersion"`, hoy `1.0.0`). Un cambio
> nativo (dependencias, permisos) sí requiere un build nuevo.

### ⚠️ Gotcha: `*.json` del `.gitignore` raíz

El `.gitignore` de la **raíz del repo** (`jarvis/`) tiene un `*.json` global. EAS
arma el archive de subida filtrando con los `.gitignore` desde el git root, así que
ese patrón **borraba `package.json` / `app.json` / `eas.json` / `package-lock.json`**
del paquete y el build fallaba en `PRE_INSTALL_HOOK` con
`package.json does not exist in build/mobile`.

El fix vive en el **`.gitignore` raíz** (no en `mobile/.gitignore`: EAS evalúa cada
`.gitignore` como un OR independiente, y la negación de un hijo no revierte la regla
del padre):

```gitignore
!mobile/*.json
!mobile/**/*.json
```

No borres esas líneas ni muevas la negación a `mobile/.gitignore`, o los builds de
EAS volverán a romperse.

## Configuración en el primer arranque

1. Abre la app → ⚙︎ Ajustes.
2. **URL del backend**: tu túnel/dominio (ej. `https://nova.tudominio.com`).
3. **API Key**: el valor de `NOVA_API_KEY` del backend (requerido al entrar por túnel;
   se omite en LAN).
4. "Probar conexión" → debe responder `✓ Conectado`.
5. Guardar.
