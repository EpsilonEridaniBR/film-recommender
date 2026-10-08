import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { SymbolView } from 'expo-symbols';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AudioExplanation } from '@/components/audio-explanation';
import { Button } from '@/components/button';
import { ThemedText } from '@/components/themed-text';
import { AUDIO_MAX_SECONDS } from '@/constants/limits';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatSeconds } from '@/utils/format';

type Props = {
  /** The finished recording, or null before recording (or after discarding it). */
  uri: string | null;
  onChange: (uri: string | null) => void;
};

/** Record a spoken explanation, up to AUDIO_MAX_SECONDS, then play it back or redo it. */
export function AudioRecorder({ uri, onChange }: Props) {
  const theme = useTheme();
  const [error, setError] = useState<string | null>(null);

  function finished(url: string | null) {
    // Only the recorder needs the microphone; turning it off clears iOS's mic indicator.
    setAudioModeAsync({ allowsRecording: false });
    if (url) onChange(url);
  }

  // Fires when recording stops, including the automatic stop at the time limit.
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY, (status) => {
    if (status.hasError) setError(status.error ?? 'Recording failed.');
    if (status.isFinished) finished(status.url);
  });
  const state = useAudioRecorderState(recorder);

  async function start() {
    setError(null);
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setError('Allow microphone access in Settings to record an explanation.');
      return;
    }
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record({ forDuration: AUDIO_MAX_SECONDS });
  }

  async function stop() {
    await recorder.stop();
    finished(recorder.uri);
  }

  if (uri && !state.isRecording) {
    return (
      <View style={styles.row}>
        <AudioExplanation uri={uri} durationMs={null} />
        <Button title="Record again" variant="plain" onPress={() => onChange(null)} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Pressable
        onPress={state.isRecording ? stop : start}
        accessibilityRole="button"
        accessibilityLabel={state.isRecording ? 'Stop recording' : 'Start recording'}
        style={({ pressed }) => [
          styles.recordButton,
          { backgroundColor: theme.backgroundElement },
          pressed && styles.pressed,
        ]}>
        <SymbolView
          name={state.isRecording ? 'stop.fill' : 'mic.fill'}
          size={28}
          tintColor={state.isRecording ? '#DC2626' : theme.tint}
        />
      </Pressable>
      <ThemedText type="small" themeColor="textSecondary">
        {state.isRecording
          ? `${formatSeconds(state.durationMillis / 1000)} / ${formatSeconds(AUDIO_MAX_SECONDS)}`
          : `Tap to record (up to ${AUDIO_MAX_SECONDS} seconds)`}
      </ThemedText>
      {error && (
        <ThemedText type="small" style={styles.error}>
          {error}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', gap: Spacing.two, paddingVertical: Spacing.two },
  row: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
  recordButton: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
  error: { color: '#DC2626', textAlign: 'center' },
});
