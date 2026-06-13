import { createAudioPlayer, setAudioModeAsync, AudioPlayer } from 'expo-audio';
import { File, Paths } from 'expo-file-system';

// Plays a queue of base64-encoded MP3 clips (TTS + filler) one after another.
// Each clip is written to a cache file because Android playback of long
// data: URIs is unreliable; file URIs are not.
export class AudioQueue {
  private queue: string[] = [];
  private current: AudioPlayer | null = null;
  private playing = false;
  private counter = 0;
  private disposed = false;

  async init() {
    // Play through the earpiece/speaker even when the silent switch is on (iOS).
    await setAudioModeAsync({ playsInSilentMode: true });
  }

  enqueue(base64Mp3: string) {
    if (!base64Mp3 || this.disposed) return;
    this.queue.push(base64Mp3);
    if (!this.playing) void this.drain();
  }

  private async drain() {
    this.playing = true;
    while (this.queue.length && !this.disposed) {
      const b64 = this.queue.shift()!;
      try {
        await this.playOne(b64);
      } catch {
        // Skip a bad clip rather than stalling the whole queue.
      }
    }
    this.playing = false;
  }

  private playOne(b64: string): Promise<void> {
    return new Promise((resolve) => {
      const file = new File(Paths.cache, `nova_tts_${this.counter++}.mp3`);
      try {
        file.write(b64, { encoding: 'base64' });
      } catch {
        resolve();
        return;
      }
      const player = createAudioPlayer({ uri: file.uri });
      this.current = player;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        sub.remove();
        try { player.remove(); } catch {}
        if (this.current === player) this.current = null;
        try { file.delete(); } catch {}
        resolve();
      };
      const sub = player.addListener('playbackStatusUpdate', (status) => {
        if (status.didJustFinish) finish();
      });
      player.play();
    });
  }

  // Stop everything immediately (barge-in / new turn).
  stop() {
    this.queue = [];
    if (this.current) {
      try { this.current.remove(); } catch {}
      this.current = null;
    }
    this.playing = false;
  }

  dispose() {
    this.disposed = true;
    this.stop();
  }
}
