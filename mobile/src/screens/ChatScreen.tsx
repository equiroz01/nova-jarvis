import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useAudioRecorder, RecordingPresets, AudioModule } from 'expo-audio';

import { theme } from '../theme';
import { Settings, getSessionId, resetSession } from '../settings';
import { AudioQueue } from '../audioQueue';
import { streamChat, streamVoice, fetchTts, ChatEvent, VoiceEvent, StreamHandle } from '../api';
import NovaFaceView, { NovaFaceHandle, NovaMode } from '../components/NovaFaceView';
import ArcReactor from '../components/ArcReactor';

type Msg = {
  id: string;
  role: 'user' | 'nova';
  text: string;
  pending?: boolean;
};

let msgSeq = 0;
const newId = () => `m${Date.now()}_${msgSeq++}`;

// VAD thresholds for hands-free mode
const VAD_SILENCE_DB = -35;
const VAD_SILENCE_MS = 1200;
const VAD_MIN_SPEECH_MS = 400;
const VAD_RESUME_DELAY_MS = 800;

export default function ChatScreen({
  settings,
  onOpenSettings,
}: {
  settings: Settings;
  onOpenSettings: () => void;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [status, setStatus] = useState<string>('');
  const [visualMode, setVisualMode] = useState<NovaMode>('idle');
  const [handsFree, setHandsFree] = useState(false);

  const sessionRef = useRef<string>('');
  const audioRef = useRef<AudioQueue | null>(null);
  const streamRef = useRef<StreamHandle | null>(null);
  const listRef = useRef<FlatList<Msg>>(null);
  const faceRef = useRef<NovaFaceHandle>(null);
  const handsFreeRef = useRef(false);
  const vadRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startListeningRef = useRef<() => void>(() => {});
  const sendVoiceRef = useRef<(uri: string) => void>(() => {});
  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true });

  const faceBaseUrl = `${settings.backendUrl}/static/face`;

  useEffect(() => { handsFreeRef.current = handsFree; }, [handsFree]);

  useEffect(() => {
    const q = new AudioQueue();
    audioRef.current = q;
    q.onActive = (active) => {
      setVisualMode(active ? 'speaking' : 'idle');
      // Auto-resume listening after NOVA finishes speaking in hands-free mode
      if (!active && handsFreeRef.current) {
        setTimeout(() => {
          if (handsFreeRef.current) startListeningRef.current();
        }, VAD_RESUME_DELAY_MS);
      }
    };
    q.init().catch(() => {});
    getSessionId().then((id) => (sessionRef.current = id));
    return () => {
      q.dispose();
      streamRef.current?.abort();
      stopVAD();
    };
  }, []);

  useEffect(() => {
    if (!settings.faceEnabled) return;
    const f = faceRef.current;
    if (!f) return;
    if (visualMode === 'speaking') f.speak();
    else if (visualMode === 'listening') f.listen();
    else if (visualMode === 'thinking') f.think(true);
    else f.idle();
  }, [visualMode, settings.faceEnabled]);

  const scrollToEnd = useCallback(() => {
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
  }, []);

  const updateMsg = useCallback((id: string, patch: Partial<Msg>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }, []);

  const appendMsg = useCallback((m: Msg) => {
    setMessages((prev) => [...prev, m]);
    scrollToEnd();
  }, [scrollToEnd]);

  // ---- Shared voice processing -------------------------------------------
  const sendVoiceRecording = useCallback((uri: string) => {
    setBusy(true);
    setStatus('Transcribiendo\u2026');
    setVisualMode('thinking');

    const userId = newId();
    appendMsg({ id: userId, role: 'user', text: '\uD83C\uDFA4 \u2026', pending: true });
    const novaId = newId();
    appendMsg({ id: novaId, role: 'nova', text: '', pending: true });

    streamRef.current = streamVoice(
      settings,
      uri,
      { session_id: sessionRef.current, language: 'es', tts: 'true' },
      {
        onEvent: (e: VoiceEvent) => {
          if (e.type === 'transcript') {
            updateMsg(userId, { text: e.transcript || '\uD83C\uDFA4 (sin audio)', pending: false });
            if (e.filler_audio_base64) audioRef.current?.enqueue(e.filler_audio_base64);
            setStatus(e.filler_text || 'NOVA est\u00e1 pensando\u2026');
            scrollToEnd();
          } else if (e.type === 'result') {
            if (e.session_id) sessionRef.current = e.session_id;
            updateMsg(userId, { text: e.transcript || '\uD83C\uDFA4 (sin audio)', pending: false });
            updateMsg(novaId, { text: e.response || '\u2026', pending: false });
            if (e.audio_base64) audioRef.current?.enqueue(e.audio_base64);
            scrollToEnd();
          } else if (e.type === 'error') {
            updateMsg(novaId, { text: `\u26A0\uFE0F ${e.detail}`, pending: false });
          }
        },
        onError: (err) => {
          updateMsg(userId, { text: '\uD83C\uDFA4 (error)', pending: false });
          updateMsg(novaId, { text: `\u26A0\uFE0F ${err.message}`, pending: false });
          setBusy(false);
          setStatus('');
          setVisualMode('idle');
          if (handsFreeRef.current) {
            setTimeout(() => { if (handsFreeRef.current) startListeningRef.current(); }, VAD_RESUME_DELAY_MS);
          }
        },
        onDone: () => {
          setBusy(false);
          setStatus('');
          if (!audioRef.current?.isPlaying()) {
            if (handsFreeRef.current) {
              setTimeout(() => { if (handsFreeRef.current) startListeningRef.current(); }, VAD_RESUME_DELAY_MS);
            } else {
              setVisualMode('idle');
            }
          }
        },
      },
    );
  }, [settings, appendMsg, updateMsg, scrollToEnd]);

  // Keep ref in sync so interval/timer callbacks always use the latest version
  useEffect(() => { sendVoiceRef.current = sendVoiceRecording; }, [sendVoiceRecording]);

  // ---- Text chat (SSE streaming) ----------------------------------------
  const sendText = useCallback(() => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    audioRef.current?.stop();

    appendMsg({ id: newId(), role: 'user', text });
    const novaId = newId();
    appendMsg({ id: novaId, role: 'nova', text: '', pending: true });
    setBusy(true);
    setStatus('NOVA est\u00e1 pensando\u2026');
    setVisualMode('thinking');

    let acc = '';
    streamRef.current = streamChat(
      settings,
      { message: text, session_id: sessionRef.current, client_id: 'mobile' },
      {
        onEvent: (e: ChatEvent) => {
          if (e.type === 'filler') {
            setStatus(e.content);
          } else if (e.type === 'token') {
            acc += e.content;
            updateMsg(novaId, { text: acc, pending: false });
            scrollToEnd();
          } else if (e.type === 'done') {
            if (e.session_id) sessionRef.current = e.session_id;
            updateMsg(novaId, { text: e.response || acc, pending: false });
          } else if (e.type === 'error') {
            updateMsg(novaId, { text: `\u26A0\uFE0F ${e.detail}`, pending: false });
          }
        },
        onError: (err) => {
          updateMsg(novaId, { text: `\u26A0\uFE0F ${err.message}`, pending: false });
          setBusy(false);
          setStatus('');
          setVisualMode('idle');
        },
        onDone: () => {
          setBusy(false);
          setStatus('');
          scrollToEnd();
          if (acc) {
            fetchTts(settings, acc).then((audio) => {
              if (audio) audioRef.current?.enqueue(audio);
              else setVisualMode('idle');
            });
          } else {
            setVisualMode('idle');
          }
        },
      },
    );
  }, [input, busy, settings, appendMsg, updateMsg, scrollToEnd]);

  // ---- Voice (push-to-talk) ---------------------------------------------
  const startRecording = useCallback(async () => {
    if (busy || handsFree) return;
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) {
      setStatus('Permiso de micr\u00f3fono denegado');
      return;
    }
    audioRef.current?.stop();
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
      setStatus('Escuchando\u2026');
      setVisualMode('listening');
    } catch (e: any) {
      setStatus(`No se pudo grabar: ${e?.message ?? e}`);
    }
  }, [busy, handsFree, recorder]);

  const stopRecording = useCallback(async () => {
    if (!recording) return;
    setRecording(false);
    try { await recorder.stop(); } catch {}
    const uri = recorder.uri;
    if (!uri) { setBusy(false); setStatus(''); return; }
    sendVoiceRecording(uri);
  }, [recording, recorder, sendVoiceRecording]);

  // ---- Hands-free (always-on listening with VAD) -------------------------
  function stopVAD() {
    if (vadRef.current) {
      clearInterval(vadRef.current);
      vadRef.current = null;
    }
  }

  function startListening() {
    if (!handsFreeRef.current) return;

    (async () => {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) {
        setStatus('Permiso de micr\u00f3fono denegado');
        handsFreeRef.current = false;
        setHandsFree(false);
        return;
      }

      audioRef.current?.stop();
      stopVAD();
      try { await recorder.stop(); } catch {}

      try {
        await recorder.prepareToRecordAsync();
        recorder.record();
      } catch (e: any) {
        setStatus(`Error de micr\u00f3fono: ${e?.message ?? e}`);
        return;
      }

      setRecording(true);
      setStatus('Escuchando\u2026');
      setVisualMode('listening');

      let speechDetected = false;
      let silenceStart = 0;
      let speechStart = 0;

      vadRef.current = setInterval(() => {
        if (!handsFreeRef.current) {
          stopVAD();
          return;
        }

        const level = recorder.currentMetering ?? -160;

        if (level > VAD_SILENCE_DB) {
          if (!speechDetected) {
            speechDetected = true;
            speechStart = Date.now();
          }
          silenceStart = 0;
        } else if (speechDetected) {
          if (silenceStart === 0) {
            silenceStart = Date.now();
          } else if (
            Date.now() - silenceStart > VAD_SILENCE_MS &&
            Date.now() - speechStart > VAD_MIN_SPEECH_MS
          ) {
            // Speech ended — stop recording and process
            stopVAD();
            setRecording(false);
            setStatus('Procesando\u2026');
            setVisualMode('thinking');
            recorder.stop().catch(() => {}).then(() => {
              const uri = recorder.uri;
              if (uri) {
                sendVoiceRef.current(uri);
              } else {
                setBusy(false);
                setStatus('');
                setVisualMode('idle');
                if (handsFreeRef.current) {
                  setTimeout(() => { if (handsFreeRef.current) startListeningRef.current(); }, VAD_RESUME_DELAY_MS);
                }
              }
            });
          }
        }
      }, 100);
    })();
  }

  // Keep ref in sync for timer/callback access
  startListeningRef.current = startListening;

  const toggleHandsFree = useCallback(async () => {
    if (handsFree) {
      handsFreeRef.current = false;
      setHandsFree(false);
      stopVAD();
      if (recording) {
        try { await recorder.stop(); } catch {}
        setRecording(false);
      }
      setVisualMode('idle');
      setStatus('');
    } else {
      if (busy) return;
      handsFreeRef.current = true;
      setHandsFree(true);
      startListening();
    }
  }, [handsFree, recording, recorder, busy]);

  const clearChat = useCallback(async () => {
    streamRef.current?.abort();
    audioRef.current?.stop();
    if (handsFree) {
      handsFreeRef.current = false;
      setHandsFree(false);
      stopVAD();
      try { await recorder.stop(); } catch {}
    }
    setMessages([]);
    setBusy(false);
    setRecording(false);
    setStatus('');
    setVisualMode('idle');
    sessionRef.current = await resetSession();
  }, [handsFree, recorder]);

  const renderItem = useCallback(({ item }: { item: Msg }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.row, isUser ? styles.rowUser : styles.rowNova]}>
        <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleNova]}>
          {item.pending && !item.text ? (
            <ActivityIndicator color={theme.accent} size="small" />
          ) : (
            <Text style={styles.bubbleText}>{item.text}</Text>
          )}
        </View>
      </View>
    );
  }, []);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
    >
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>N.O.V.A.</Text>
          <Text style={styles.subtitle}>{status || 'Listo'}</Text>
        </View>
        <View style={styles.headerBtns}>
          <Pressable
            onPress={toggleHandsFree}
            style={[styles.iconBtn, handsFree && styles.iconBtnActive]}
            hitSlop={8}
            disabled={busy && !handsFree}
          >
            <Text style={[styles.iconTxt, handsFree && styles.iconTxtActive]}>
              {handsFree ? '\u23F9' : '\uD83C\uDF99'}
            </Text>
          </Pressable>
          <Pressable onPress={clearChat} style={styles.iconBtn} hitSlop={8}>
            <Text style={styles.iconTxt}>{'\uFF0B'}</Text>
          </Pressable>
          <Pressable onPress={onOpenSettings} style={styles.iconBtn} hitSlop={8}>
            <Text style={styles.iconTxt}>{'\u2699\uFE0E'}</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.facePanel}>
        {settings.faceEnabled ? (
          <NovaFaceView
            ref={faceRef}
            baseUrl={faceBaseUrl}
            emotion="neutral"
            style={styles.faceWeb}
            onReady={() => {
              const f = faceRef.current;
              if (!f) return;
              if (visualMode === 'speaking') f.speak();
              else if (visualMode === 'listening') f.listen();
              else if (visualMode === 'thinking') f.think(true);
              else f.idle();
            }}
          />
        ) : (
          <ArcReactor mode={visualMode} size={200} />
        )}
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Hola, Se\u00f1or.</Text>
            <Text style={styles.emptyText}>
              Escriba un mensaje o mantenga presionado el micr\u00f3fono para hablar.
            </Text>
          </View>
        }
        onContentSizeChange={scrollToEnd}
      />

      {handsFree ? (
        <View style={styles.inputBar}>
          <View style={styles.handsFreeLabel}>
            <Text style={styles.handsFreeIcon}>{'\uD83C\uDF99'}</Text>
            <Text style={styles.handsFreeText}>Manos libres</Text>
          </View>
          <Pressable style={styles.stopBtn} onPress={toggleHandsFree}>
            <Text style={styles.stopTxt}>Detener</Text>
          </Pressable>
        </View>
      ) : (
        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Mensaje a NOVA\u2026"
            placeholderTextColor={theme.textDim}
            multiline
            editable={!busy}
            onSubmitEditing={sendText}
          />
          {input.trim() ? (
            <Pressable
              style={[styles.sendBtn, busy && styles.btnDisabled]}
              onPress={sendText}
              disabled={busy}
            >
              <Text style={styles.sendTxt}>{'\u27A4'}</Text>
            </Pressable>
          ) : (
            <Pressable
              style={[styles.micBtn, recording && styles.micBtnActive, busy && styles.btnDisabled]}
              onPressIn={startRecording}
              onPressOut={stopRecording}
              disabled={busy}
            >
              <Text style={styles.micTxt}>{recording ? '\u25CF' : '\uD83C\uDFA4'}</Text>
            </Pressable>
          )}
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: theme.bg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.border,
    backgroundColor: theme.surface,
  },
  title: { color: theme.accent, fontSize: 20, fontWeight: '700', letterSpacing: 2 },
  subtitle: { color: theme.textDim, fontSize: 12, marginTop: 2 },
  headerBtns: { flexDirection: 'row', gap: 8 },
  iconBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: theme.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconBtnActive: {
    backgroundColor: theme.accent,
  },
  iconTxt: { color: theme.text, fontSize: 18 },
  iconTxtActive: { color: theme.bg },
  facePanel: {
    height: 240,
    backgroundColor: theme.bg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.border,
  },
  faceWeb: { flex: 1, backgroundColor: 'transparent' },
  listContent: { padding: 16, flexGrow: 1 },
  row: { marginVertical: 4, flexDirection: 'row' },
  rowUser: { justifyContent: 'flex-end' },
  rowNova: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '82%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: theme.radius },
  bubbleUser: { backgroundColor: theme.userBubble, borderBottomRightRadius: 4 },
  bubbleNova: { backgroundColor: theme.novaBubble, borderBottomLeftRadius: 4 },
  bubbleText: { color: theme.text, fontSize: 16, lineHeight: 22 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 40 },
  emptyTitle: { color: theme.accent, fontSize: 22, fontWeight: '600', marginBottom: 8 },
  emptyText: { color: theme.textDim, fontSize: 15, textAlign: 'center', lineHeight: 21 },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.border,
    backgroundColor: theme.surface,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    backgroundColor: theme.surfaceAlt,
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingTop: 11,
    paddingBottom: 11,
    color: theme.text,
    fontSize: 16,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendTxt: { color: theme.bg, fontSize: 18, fontWeight: '700' },
  micBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.surfaceAlt,
    borderWidth: 1,
    borderColor: theme.accentDim,
    alignItems: 'center',
    justifyContent: 'center',
  },
  micBtnActive: { backgroundColor: theme.danger, borderColor: theme.danger },
  micTxt: { fontSize: 18, color: theme.text },
  btnDisabled: { opacity: 0.4 },
  handsFreeLabel: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    height: 44,
  },
  handsFreeIcon: { fontSize: 20 },
  handsFreeText: { color: theme.accent, fontSize: 16, fontWeight: '600' },
  stopBtn: {
    height: 44,
    paddingHorizontal: 20,
    borderRadius: 22,
    backgroundColor: theme.danger,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stopTxt: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
