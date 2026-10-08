import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import type { FilmSearchResult, FilmSummary } from '@/api/films';
import { Poster } from '@/components/poster';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

export const FILM_ROW_POSTER_WIDTH = 46;

/** "2016 · Denis Villeneuve" */
export function filmMeta(film: Pick<FilmSummary, 'year' | 'directors'>) {
  return [film.year, film.directors.join(', ')].filter(Boolean).join(' · ');
}

type Props = {
  film: FilmSearchResult;
  /** What tapping the row does; by default, open the film. */
  onPress?: (film: FilmSearchResult) => void;
};

/** A search result: poster on the left; title, year and director, then top actors on the right. */
export function FilmRow({ film, onPress }: Props) {
  const router = useRouter();
  // Missing from responses by older servers (or cached before it was added).
  const topCast = film.top_cast ?? [];
  return (
    // Navigate on press rather than wrapping in <Link asChild>, which drops
    // Pressable's style callback (and with it the row layout).
    <Pressable
      onPress={() =>
        onPress
          ? onPress(film)
          : router.push({ pathname: '/film/[tmdbId]', params: { tmdbId: film.tmdb_id } })
      }
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
      <Poster uri={film.poster_url} width={FILM_ROW_POSTER_WIDTH} />
      <View style={styles.text}>
        <ThemedText numberOfLines={2}>{film.title}</ThemedText>
        {film.matched_title ? (
          // Why this result matched, e.g. the original title of a foreign film.
          <ThemedText
            type="small"
            themeColor="textSecondary"
            style={styles.matchedTitle}
            numberOfLines={1}>
            aka: {film.matched_title}
          </ThemedText>
        ) : null}
        <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
          {filmMeta(film)}
        </ThemedText>
        {topCast.length > 0 && (
          <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
            {topCast.join(', ')}
          </ThemedText>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
  },
  pressed: { opacity: 0.6 },
  text: { flex: 1, gap: Spacing.half },
  matchedTitle: { fontStyle: 'italic' },
});
