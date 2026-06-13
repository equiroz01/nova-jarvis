import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';

const KEY_URL = 'nova_backend_url';
const KEY_API = 'nova_api_key';
const KEY_SESSION = 'nova_session_id';

// Sensible default; the user overrides this in Settings to point at their tunnel.
export const DEFAULT_BACKEND_URL = 'https://nova.example.com';

export type Settings = {
  backendUrl: string;
  apiKey: string;
};

function normalizeUrl(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

export async function loadSettings(): Promise<Settings> {
  const [url, apiKey] = await Promise.all([
    SecureStore.getItemAsync(KEY_URL),
    SecureStore.getItemAsync(KEY_API),
  ]);
  return {
    backendUrl: url ? normalizeUrl(url) : DEFAULT_BACKEND_URL,
    apiKey: apiKey ?? '',
  };
}

export async function saveSettings(s: Settings): Promise<Settings> {
  const normalized: Settings = {
    backendUrl: normalizeUrl(s.backendUrl),
    apiKey: s.apiKey.trim(),
  };
  await Promise.all([
    SecureStore.setItemAsync(KEY_URL, normalized.backendUrl),
    SecureStore.setItemAsync(KEY_API, normalized.apiKey),
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
