import { Settings } from './settings';

// React Native's fetch cannot stream a response body (no getReader()), so we
// drive streaming endpoints with XMLHttpRequest and parse the text as it grows.
// This handles both SSE (`data: {...}\n\n`) and NDJSON (`{...}\n`) line formats.

export type StreamHandle = { abort: () => void };

type StreamOpts = {
  settings: Settings;
  path: string;
  method?: 'GET' | 'POST';
  jsonBody?: unknown;
  formBody?: FormData;
  onEvent: (obj: any) => void;
  onError: (err: Error) => void;
  onDone: () => void;
};

function authHeaders(s: Settings): Record<string, string> {
  return s.apiKey ? { Authorization: `Bearer ${s.apiKey}` } : {};
}

function parseChunk(text: string): any[] {
  // Split into complete lines; the caller passes only the newly-arrived slice.
  const out: any[] = [];
  for (const raw of text.split('\n')) {
    let line = raw.trim();
    if (!line) continue;
    if (line.startsWith('data:')) line = line.slice(5).trim();
    if (!line.startsWith('{')) continue; // skip SSE padding/comments
    try {
      out.push(JSON.parse(line));
    } catch {
      // Partial JSON across chunk boundary — ignore; it arrives complete later.
    }
  }
  return out;
}

export function streamLines(opts: StreamOpts): StreamHandle {
  const { settings, path, method = 'POST', jsonBody, formBody, onEvent, onError, onDone } = opts;
  const xhr = new XMLHttpRequest();
  const url = `${settings.backendUrl}${path}`;
  xhr.open(method, url);

  for (const [k, v] of Object.entries(authHeaders(settings))) xhr.setRequestHeader(k, v);
  if (jsonBody !== undefined) xhr.setRequestHeader('Content-Type', 'application/json');
  // For FormData we let XHR set the multipart boundary automatically.

  // Track how much of responseText we've already consumed.
  let consumed = 0;
  let pending = '';
  let settled = false;

  const flush = (final: boolean) => {
    const fresh = xhr.responseText.slice(consumed);
    consumed = xhr.responseText.length;
    pending += fresh;
    // Keep the trailing partial line in `pending` until a newline lands.
    const lastNl = pending.lastIndexOf('\n');
    if (lastNl === -1 && !final) return;
    const ready = final ? pending : pending.slice(0, lastNl + 1);
    pending = final ? '' : pending.slice(lastNl + 1);
    for (const obj of parseChunk(ready)) onEvent(obj);
  };

  xhr.onreadystatechange = () => {
    if (xhr.readyState === XMLHttpRequest.LOADING) flush(false);
  };
  xhr.onprogress = () => flush(false);

  xhr.onload = () => {
    if (settled) return;
    settled = true;
    if (xhr.status >= 200 && xhr.status < 300) {
      flush(true);
      onDone();
    } else {
      let detail = `HTTP ${xhr.status}`;
      try {
        const j = JSON.parse(xhr.responseText);
        if (j?.detail) detail = j.detail;
      } catch {}
      onError(new Error(detail));
    }
  };
  xhr.onerror = () => {
    if (settled) return;
    settled = true;
    onError(new Error('Sin conexión con el backend. Revisa la URL en Ajustes.'));
  };
  xhr.ontimeout = () => {
    if (settled) return;
    settled = true;
    onError(new Error('La petición tardó demasiado.'));
  };

  xhr.timeout = 120000;

  if (jsonBody !== undefined) xhr.send(JSON.stringify(jsonBody));
  else if (formBody) xhr.send(formBody as any);
  else xhr.send();

  return { abort: () => { settled = true; xhr.abort(); } };
}

// ---- Typed event shapes -------------------------------------------------

export type ChatEvent =
  | { type: 'filler'; content: string }
  | { type: 'token'; content: string }
  | { type: 'done'; response: string; session_id: string }
  | { type: 'error'; detail: string };

export type VoiceEvent =
  | { type: 'transcript'; transcript: string; query_type: string; filler_text: string; filler_audio_base64: string }
  | { type: 'result'; transcript: string; response: string; audio_base64: string; session_id: string }
  | { type: 'error'; detail: string };

// ---- High-level calls ---------------------------------------------------

export function streamChat(
  settings: Settings,
  body: { message: string; session_id: string; client_id: string },
  handlers: { onEvent: (e: ChatEvent) => void; onError: (e: Error) => void; onDone: () => void },
): StreamHandle {
  return streamLines({
    settings,
    path: '/chat/stream',
    jsonBody: body,
    onEvent: handlers.onEvent as (o: any) => void,
    onError: handlers.onError,
    onDone: handlers.onDone,
  });
}

export function streamVoice(
  settings: Settings,
  audioUri: string,
  fields: { session_id: string; language: string; tts: string },
  handlers: { onEvent: (e: VoiceEvent) => void; onError: (e: Error) => void; onDone: () => void },
): StreamHandle {
  const form = new FormData();
  // RN FormData accepts a file descriptor object for multipart uploads.
  form.append('audio', {
    uri: audioUri,
    name: 'speech.m4a',
    type: 'audio/m4a',
  } as any);
  form.append('session_id', fields.session_id);
  form.append('language', fields.language);
  form.append('tts', fields.tts);
  return streamLines({
    settings,
    path: '/voice/stream',
    formBody: form,
    onEvent: handlers.onEvent as (o: any) => void,
    onError: handlers.onError,
    onDone: handlers.onDone,
  });
}

export async function checkHealth(settings: Settings): Promise<{ ok: boolean; detail: string }> {
  try {
    const res = await fetch(`${settings.backendUrl}/health`, { headers: authHeaders(settings) });
    const body = await res.json().catch(() => ({}));
    if (res.ok) return { ok: true, detail: body?.status ? `status: ${body.status}` : 'ok' };
    return { ok: false, detail: body?.detail || `HTTP ${res.status}` };
  } catch (e: any) {
    return { ok: false, detail: e?.message || 'sin conexión' };
  }
}
