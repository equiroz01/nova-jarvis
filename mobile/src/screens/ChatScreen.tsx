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
import { streamChat, streamVoice, ChatEvent, VoiceEvent, StreamHandle } from '../api';
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
  // Single source of truth for the visualizer state (reactor + face both read it).
  const [visualMode, setVisualMode] = useState<NovaMode>('idle');

  const sessionRef = useRef<string>('');
  const audioRef = useRef<AudioQueue | null>(null);
  const streamRef = useRef<StreamHandle | null>(null);
  const listRef = useRef<FlatList<Msg>>(null);
  const faceRef = useRef<NovaFaceHandle>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  const faceBaseUrl = `${settings.backendUrl}/static/face`;

  useEffect(() => {
    const q = new AudioQueue();
    audioRef.current = q;
    // Drive the visualizer's speaking state from real TTS playback.
    q.onActive = (active) => setVisualMode(active ? 'speaking' : 'idle');
    q.init().catch(() => {});
    getSessionId().then((id) => (sessionRef.current = id));
    return () => {
      q.dispose();
      streamRef.current?.abort();
    };
  }, []);

  // Push visualMode to the face WebView (imperative bridge). The reactor reads
  // visualMode directly as a prop, so it needs no equivalent.
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
    setStatus('NOVA está pensando…');
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
            updateMsg(novaId, { text: `⚠️ ${e.detail}`, pending: false });
          }
        },
        onError: (err) => {
          updateMsg(novaId, { text: `⚠️ ${err.message}`, pending: false });
          setBusy(false);
          setStatus('');
          setVisualMode('idle');
        },
        onDone: () => {
          setBusy(false);
          setStatus('');
          scrollToEnd();
          // No TTS on the text path → return to idle (speak() takes over if audio plays).
          setVisualMode('idle');
        },
      },
    );
  }, [input, busy, settings, appendMsg, updateMsg, scrollToEnd]);

  // ---- Voice (push-to-talk) ---------------------------------------------
  const startRecording = useCallback(async () => {
    if (busy) return;
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) {
      setStatus('Permiso de micrófono denegado');
      return;
    }
    audioRef.current?.stop();
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
      setStatus('Escuchando…');
      setVisualMode('listening');
    } catch (e: any) {
      setStatus(`No se pudo grabar: ${e?.message ?? e}`);
    }
  }, [busy, recorder]);

  const stopRecording = useCallback(async () => {
    if (!recording) return;
    setRecording(false);
    setBusy(true);
    setStatus('Transcribiendo…');
    setVisualMode('thinking');
    try {
      await recorder.stop();
    } catch {}
    const uri = recorder.uri;
    if (!uri) {
      setBusy(false);
      setStatus('');
      return;
    }

    const userId = newId();
    appendMsg({ id: userId, role: 'user', text: '🎤 …', pending: true });
    const novaId = newId();
    appendMsg({ id: novaId, role: 'nova', text: '', pending: true });

    streamRef.current = streamVoice(
      settings,
      uri,
      { session_id: sessionRef.current, language: 'es', tts: 'true' },
      {
        onEvent: (e: VoiceEvent) => {
          if (e.type === 'transcript') {
            updateMsg(userId, { text: e.transcript || '🎤 (sin audio)', pending: false });
            if (e.filler_audio_base64) audioRef.current?.enqueue(e.filler_audio_base64);
            setStatus(e.filler_text || 'NOVA está pensando…');
            scrollToEnd();
          } else if (e.type === 'result') {
            if (e.session_id) sessionRef.current = e.session_id;
            updateMsg(userId, { text: e.transcript || '🎤 (sin audio)', pending: false });
            updateMsg(novaId, { text: e.response || '…', pending: false });
            if (e.audio_base64) audioRef.current?.enqueue(e.audio_base64);
            scrollToEnd();
          } else if (e.type === 'error') {
            updateMsg(novaId, { text: `⚠️ ${e.detail}`, pending: false });
          }
        },
        onError: (err) => {
          updateMsg(userId, { text: '🎤 (error)', pending: false });
          updateMsg(novaId, { text: `⚠️ ${err.message}`, pending: false });
          setBusy(false);
          setStatus('');
          setVisualMode('idle');
        },
        onDone: () => {
          setBusy(false);
          setStatus('');
          // If TTS is playing, AudioQueue.onActive returns the face to idle when
          // it finishes; otherwise drop the thinking state now.
          if (!audioRef.current?.isPlaying()) setVisualMode('idle');
        },
      },
    );
  }, [recording, recorder, settings, appendMsg, updateMsg, scrollToEnd]);

  const clearChat = useCallback(async () => {
    streamRef.current?.abort();
    audioRef.current?.stop();
    setMessages([]);
    setBusy(false);
    setStatus('');
    setVisualMode('idle');
    sessionRef.current = await resetSession();
  }, []);

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
          <Pressable onPress={clearChat} style={styles.iconBtn} hitSlop={8}>
            <Text style={styles.iconTxt}>＋</Text>
          </Pressable>
          <Pressable onPress={onOpenSettings} style={styles.iconBtn} hitSlop={8}>
            <Text style={styles.iconTxt}>⚙︎</Text>
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
              // Re-apply the current state once the WebView is live.
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
            <Text style={styles.emptyTitle}>Hola, Señor.</Text>
            <Text style={styles.emptyText}>
              Escriba un mensaje o mantenga presionado el micrófono para hablar.
            </Text>
          </View>
        }
        onContentSizeChange={scrollToEnd}
      />

      <View style={styles.inputBar}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Mensaje a NOVA…"
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
            <Text style={styles.sendTxt}>➤</Text>
          </Pressable>
        ) : (
          <Pressable
            style={[styles.micBtn, recording && styles.micBtnActive, busy && styles.btnDisabled]}
            onPressIn={startRecording}
            onPressOut={stopRecording}
            disabled={busy}
          >
            <Text style={styles.micTxt}>{recording ? '●' : '🎤'}</Text>
          </Pressable>
        )}
      </View>
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
  iconTxt: { color: theme.text, fontSize: 18 },
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
    alignItems: 'flex-end',
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
});
