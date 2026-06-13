import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { theme } from './src/theme';
import { Settings, loadSettings } from './src/settings';
import ChatScreen from './src/screens/ChatScreen';
import SettingsScreen from './src/screens/SettingsScreen';

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    loadSettings().then(setSettings);
  }, []);

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        {settings ? (
          <ChatScreen settings={settings} onOpenSettings={() => setShowSettings(true)} />
        ) : (
          <View style={styles.loading}>
            <ActivityIndicator color={theme.accent} size="large" />
          </View>
        )}
      </SafeAreaView>

      <Modal
        visible={showSettings}
        animationType="slide"
        presentationStyle="fullScreen"
        onRequestClose={() => setShowSettings(false)}
      >
        <SafeAreaProvider>
          <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
            {settings && (
              <SettingsScreen
                initial={settings}
                onSaved={setSettings}
                onClose={() => setShowSettings(false)}
              />
            )}
          </SafeAreaView>
        </SafeAreaProvider>
      </Modal>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.bg },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.bg },
});
