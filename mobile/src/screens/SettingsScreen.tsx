import React, { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';

import { theme } from '../theme';
import { Settings, saveSettings } from '../settings';
import { checkHealth } from '../api';

export default function SettingsScreen({
  initial,
  onSaved,
  onClose,
}: {
  initial: Settings;
  onSaved: (s: Settings) => void;
  onClose: () => void;
}) {
  const [url, setUrl] = useState(initial.backendUrl);
  const [apiKey, setApiKey] = useState(initial.apiKey);
  const [faceEnabled, setFaceEnabled] = useState(initial.faceEnabled);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const test = async () => {
    setTesting(true);
    setResult(null);
    const r = await checkHealth({ backendUrl: url.trim().replace(/\/+$/, ''), apiKey: apiKey.trim() });
    setResult(r);
    setTesting(false);
  };

  const save = async () => {
    const saved = await saveSettings({ backendUrl: url, apiKey, faceEnabled });
    onSaved(saved);
    onClose();
  };

  return (
    <View style={styles.flex}>
      <View style={styles.header}>
        <Text style={styles.title}>Ajustes</Text>
        <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
          <Text style={styles.closeTxt}>✕</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.label}>URL del backend</Text>
        <Text style={styles.hint}>Tu túnel o dominio público, p. ej. https://nova.midominio.com</Text>
        <TextInput
          style={styles.input}
          value={url}
          onChangeText={setUrl}
          placeholder="https://…"
          placeholderTextColor={theme.textDim}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />

        <Text style={[styles.label, { marginTop: 24 }]}>API Key</Text>
        <Text style={styles.hint}>Valor de NOVA_API_KEY. Requerido cuando entras por túnel.</Text>
        <TextInput
          style={styles.input}
          value={apiKey}
          onChangeText={setApiKey}
          placeholder="Bearer token…"
          placeholderTextColor={theme.textDim}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
        />

        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.label}>NOVA Face</Text>
            <Text style={styles.hint}>
              Muestra el avatar animado en lugar del encabezado. Reacciona al hablar,
              escuchar y pensar.
            </Text>
          </View>
          <Switch
            value={faceEnabled}
            onValueChange={setFaceEnabled}
            trackColor={{ false: theme.border, true: theme.accentDim }}
            thumbColor={faceEnabled ? theme.accent : theme.textDim}
          />
        </View>

        <Pressable style={styles.testBtn} onPress={test} disabled={testing}>
          {testing ? (
            <ActivityIndicator color={theme.accent} size="small" />
          ) : (
            <Text style={styles.testTxt}>Probar conexión</Text>
          )}
        </Pressable>

        {result && (
          <View
            style={[
              styles.resultBox,
              { borderColor: result.ok ? theme.accentDim : theme.danger },
            ]}
          >
            <Text style={{ color: result.ok ? theme.accent : theme.danger, fontWeight: '600' }}>
              {result.ok ? '✓ Conectado' : '✕ Error'}
            </Text>
            <Text style={styles.resultDetail}>{result.detail}</Text>
          </View>
        )}
      </ScrollView>

      <View style={styles.footer}>
        <Pressable style={styles.saveBtn} onPress={save}>
          <Text style={styles.saveTxt}>Guardar</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: theme.bg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.border,
    backgroundColor: theme.surface,
  },
  title: { color: theme.text, fontSize: 20, fontWeight: '700' },
  closeBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: theme.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeTxt: { color: theme.text, fontSize: 16 },
  content: { padding: 20 },
  label: { color: theme.text, fontSize: 16, fontWeight: '600', marginBottom: 4 },
  hint: { color: theme.textDim, fontSize: 13, marginBottom: 10, lineHeight: 18 },
  input: {
    backgroundColor: theme.surfaceAlt,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: theme.text,
    fontSize: 16,
    borderWidth: 1,
    borderColor: theme.border,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 24,
    gap: 12,
  },
  switchText: { flex: 1 },
  testBtn: {
    marginTop: 24,
    backgroundColor: theme.surfaceAlt,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: theme.accentDim,
  },
  testTxt: { color: theme.accent, fontSize: 16, fontWeight: '600' },
  resultBox: {
    marginTop: 16,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    backgroundColor: theme.surface,
  },
  resultDetail: { color: theme.textDim, fontSize: 13, marginTop: 4 },
  footer: {
    padding: 16,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.border,
    backgroundColor: theme.surface,
  },
  saveBtn: {
    backgroundColor: theme.accent,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  saveTxt: { color: theme.bg, fontSize: 17, fontWeight: '700' },
});
