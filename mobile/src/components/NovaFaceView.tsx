/**
 * NovaFaceView.tsx — vendored copy of packages/nova-face/mobile/NovaFaceView.tsx.
 *
 * Vendored (not imported across the repo root) on purpose: EAS treats mobile/
 * as the project root, and Metro doesn't watch sibling folders without extra
 * config — duplicating this thin bridge keeps the build self-contained. The
 * heavy parts (the face core + webview-host.html + PNG assets) are NOT bundled;
 * they load over HTTP from the backend at `${baseUrl}` (= /static/face).
 *
 * Keep in sync with the package version if the bridge protocol changes.
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
  /** Base URL where the backend serves the package, no trailing slash. e.g. https://api/static/face */
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
      androidLayerType={Platform.OS === 'android' ? 'hardware' : undefined}
    />
  );
});

const styles = StyleSheet.create({
  // Transparent background so the avatar blends with the app's dark surface.
  web: { flex: 1, backgroundColor: 'transparent' },
});

export default NovaFaceView;
