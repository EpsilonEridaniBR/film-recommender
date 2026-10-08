import { useRouter } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, View } from 'react-native';

import type { Suggestion } from '@/api/films';
import { AudioExplanation } from '@/components/audio-explanation';
import { FilmHeading } from '@/components/film-heading';
import { LARGE_POSTER_WIDTH, Poster } from '@/components/poster';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = {
  suggestion: Suggestion;
  /** Shows a "…" button that opens the edit actions. */
  onMore?: () => void;
};

/** One suggested film with the reason it was suggested. */
export function SuggestionCard({ suggestion, onMore }: Props) {
  const theme = useTheme();
  const router = useRouter();
  const { film } = suggestion;

  return (
    <Pressable
      onPress={() => router.push({ pathname: '/film/[tmdbId]', params: { tmdbId: film.tmdb_id } })}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <Poster uri={film.poster_url} width={LARGE_POSTER_WIDTH} />
      <View style={styles.body}>
        <FilmHeading
          title={film.title}
          originalTitle={film.original_title}
          year={film.year}
          runtime={film.runtime}
          directors={film.directors}
          topCast={film.top_cast ?? []}
        />
        {suggestion.audio_url ? (
          <AudioExplanation
            uri={suggestion.audio_url}
            durationMs={suggestion.audio_duration_ms ?? null}
          />
        ) : (
          <ThemedText type="small">{suggestion.explanation}</ThemedText>
        )}
        {suggestion.recommended_by && (
          <ThemedText type="small" themeColor="textSecondary">
            — {suggestion.recommended_by}
          </ThemedText>
        )}
      </View>
      {onMore && (
        <Pressable
          onPress={onMore}
          accessibilityLabel="Change this suggestion"
          hitSlop={12}
          style={({ pressed }) => pressed && styles.pressed}>
          <SymbolView name="ellipsis" size={18} tintColor={theme.textSecondary} />
        </Pressable>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  pressed: { opacity: 0.7 },
  body: { flex: 1, gap: Spacing.two },
});
