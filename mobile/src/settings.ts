import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';

const KEY_URL = 'nova_backend_url';
const KEY_API = 'nova_api_key';
const KEY_SESSION = 'nova_session_id';
const KEY_FACE = 'nova_face_enabled';

// Sensible default; the user overrides this in Settings to point at their tunnel.
export const DEFAULT_BACKEND_URL = 'https://nova.example.com';

export type Settings = {
  backendUrl: string;
  apiKey: string;
  // NOVA Face avatar visualizer. Off by default → zero cost (no WebView).
  faceEnabled: boolean;
};

function normalizeUrl(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

export async function loadSettings(): Promise<Settings> {
  const [url, apiKey, face] = await Promise.all([
    SecureStore.getItemAsync(KEY_URL),
    SecureStore.getItemAsync(KEY_API),
    SecureStore.getItemAsync(KEY_FACE),
  ]);
  return {
    backendUrl: url ? normalizeUrl(url) : DEFAULT_BACKEND_URL,
    apiKey: apiKey ?? '',
    faceEnabled: face === '1',
  };
}

export async function saveSettings(s: Settings): Promise<Settings> {
  const normalized: Settings = {
    backendUrl: normalizeUrl(s.backendUrl),
    apiKey: s.apiKey.trim(),
    faceEnabled: !!s.faceEnabled,
  };
  await Promise.all([
    SecureStore.setItemAsync(KEY_URL, normalized.backendUrl),
    SecureStore.setItemAsync(KEY_API, normalized.apiKey),
    SecureStore.setItemAsync(KEY_FACE, normalized.faceEnabled ? '1' : '0'),
  ]);
  return normalized;
}

// One stable session id per install (until the user starts a new conversation).
export async function getSessionId(): Promise<string> {
  let id = await SecureStore.getItemAsync(KEY_SESSION);
  if (!id) {
    id = Crypto.randomUUID();
    await SecureStore.setItemAsync(KEY_SESSION, id);
  }
  return id;
}

export async function resetSession(): Promise<string> {
  const id = Crypto.randomUUID();
  await SecureStore.setItemAsync(KEY_SESSION, id);
  return id;
}
