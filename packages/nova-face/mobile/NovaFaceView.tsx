/**
 * NovaFaceView.tsx — wrapper React Native (Expo) del módulo NovaFace.
 *
 * Hospeda la cara web (canvas + Web Audio) dentro de un WebView y la controla
 * por postMessage. Reutiliza el MISMO core que la web — cero reescritura.
 *
 * Requisito:  expo install react-native-webview
 *
 * Uso:
 *   import { NovaFaceView, NovaFaceHandle } from '@nova/face/mobile/NovaFaceView';
 *
 *   const faceRef = useRef<NovaFaceHandle>(null);
 *   <NovaFaceView
 *     ref={faceRef}
 *     baseUrl="https://tu-backend/static/face"
 *     emotion="neutral"
 *     onReady={() => faceRef.current?.setEmotion('happy')}
 *   />
 *
 *   // desde tu lógica de voz/chat:
 *   faceRef.current?.think(true);          // procesando / backend
 *   faceRef.current?.setMode('speaking');  // empezó a hablar
 *   faceRef.current?.setLevel(0.6);        // empuja amplitud (0..1) mientras habla
 *   faceRef.current?.idle();
 *
 * Lip-sync en móvil: como el audio se reproduce con expo-audio (nativo), empuja
 * la amplitud con setLevel() desde el metering de expo-audio. Si prefieres que
 * el WebView capture el micrófono directamente, sirve el host por https y pásale
 * permisos de micrófono al WebView.
 */
import React, { forwardRef, useImperativeHandle, useRef, useCallback } from 'react';
import { StyleSheet, ViewStyle, Platform } from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';

export type NovaMode = 'idle' | 'speaking' | 'listening' | 'thinking';
export type NovaEmotion =
  | 'neutral' | 'happy' | 'love' | 'cool' | 'sad' | 'angry' | 'surprised' | 'sleepy' | 'dizzy';

export interface NovaFaceHandle {
  setMode(mode: NovaMode): void;
  setEmotion(emotion: NovaEmotion): void;
  setLevel(level: number): void;
  think(on?: boolean): void;
  speak(): void;
  listen(): void;
  idle(): void;
  setStatus(text: string | null): void;
}

export interface NovaFaceProps {
  /** Base URL donde el backend sirve el paquete, sin slash final. Ej: https://api/static/face */
  baseUrl: string;
  emotion?: NovaEmotion;
  hud?: boolean;
  style?: ViewStyle;
  onReady?: () => void;
  onModeChange?: (mode: NovaMode) => void;
  onEmotionChange?: (emotion: NovaEmotion) => void;
  onStatus?: (text: string) => void;
}

export const NovaFaceView = forwardRef<NovaFaceHandle, NovaFaceProps>(function NovaFaceView(
  { baseUrl, emotion = 'neutral', hud = true, style, onReady, onModeChange, onEmotionChange, onStatus },
  ref
) {
  const webRef = useRef<WebView>(null);

  const send = useCallback((cmd: string, value?: unknown) => {
    const js = `(function(){window.dispatchEvent(new MessageEvent('message',{data:${JSON.stringify(
      JSON.stringify({ type: 'nova', cmd, value })
    )}}));})();true;`;
    webRef.current?.injectJavaScript(js);
  }, []);

  useImperativeHandle(ref, () => ({
    setMode: (m) => send('setMode', m),
    setEmotion: (e) => send('setEmotion', e),
    setLevel: (l) => send('setLevel', l),
    think: (on = true) => send('think', on),
    speak: () => send('speak'),
    listen: () => send('listen'),
    idle: () => send('idle'),
    setStatus: (t) => send('status', t),
  }), [send]);

  const onMessage = useCallback((e: WebViewMessageEvent) => {
    let msg: any;
    try { msg = JSON.parse(e.nativeEvent.data); } catch { return; }
    if (!msg || msg.type !== 'nova') return;
    switch (msg.event) {
      case 'ready': onReady?.(); break;
      case 'modechange': onModeChange?.(msg.value); break;
      case 'emotionchange': onEmotionChange?.(msg.value); break;
      case 'status': onStatus?.(msg.value); break;
    }
  }, [onReady, onModeChange, onEmotionChange, onStatus]);

  const uri = `${baseUrl}/mobile/webview-host.html?assets=${encodeURIComponent(
    baseUrl + '/assets/'
  )}&emotion=${emotion}&hud=${hud ? 1 : 0}`;

  return (
    <WebView
      ref={webRef}
      source={{ uri }}
      style={[styles.web, style]}
      originWhitelist={['*']}
      onMessage={onMessage}
      javaScriptEnabled
      domStorageEnabled
      mediaPlaybackRequiresUserAction={false}
      allowsInlineMediaPlayback
      scrollEnabled={false}
      bounces={false}
      // fondo transparente para que combine con la app
      backgroundColor="transparent"
      androidLayerType={Platform.OS === 'android' ? 'hardware' : undefined}
    />
  );
});

const styles = StyleSheet.create({
  web: { flex: 1, backgroundColor: 'transparent' },
});

export default NovaFaceView;
