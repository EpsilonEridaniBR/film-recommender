import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatSeconds } from '@/utils/format';

/** Play/pause button for a recorded explanation. */
export function AudioExplanation({ uri, durationMs }: { uri: string; durationMs: number | null }) {
  const theme = useTheme();
  const player = useAudioPlayer(uri);
  const status = useAudioPlayerStatus(player);

  const total = status.duration || (durationMs ?? 0) / 1000;
  const label = status.playing
    ? `${formatSeconds(status.currentTime)} / ${formatSeconds(total)}`
    : formatSeconds(total);

  function toggle() {
    if (status.playing) {
      player.pause();
      return;
    }
    if (status.didJustFinish || (total > 0 && status.currentTime >= total)) {
      player.seekTo(0);
    }
    player.play();
  }

  return (
    <Pressable
      onPress={toggle}
      accessibilityRole="button"
      accessibilityLabel={status.playing ? 'Pause explanation' : 'Play explanation'}
      style={[styles.button, { backgroundColor: theme.backgroundElement }]}>
      <SymbolView
        name={status.playing ? 'pause.fill' : 'play.fill'}
        size={14}
        tintColor={theme.tint}
      />
      <ThemedText type="small">{label}</ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
  },
});
