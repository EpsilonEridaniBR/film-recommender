import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import type { Edit } from '@/api/edits';
import { AudioExplanation } from '@/components/audio-explanation';
import { FILM_ROW_POSTER_WIDTH } from '@/components/film-row';
import { Poster } from '@/components/poster';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

/** "Replace Arrival with Up", "Update the explanation for Up", … */
export function describeEdit(edit: Edit) {
  const proposed = edit.proposed_film?.title;
  const replaced = edit.replaced_film?.title;
  switch (edit.action) {
    case 'add':
      return `Add ${proposed}`;
    case 'remove':
      return `Remove ${replaced}`;
    case 'replace':
      return edit.proposed_film?.tmdb_id === edit.replaced_film?.tmdb_id
        ? `Update the explanation for ${replaced}`
        : `Replace ${replaced} with ${proposed}`;
  }
}

/** One proposed change: which film, what changes, why, and who proposed it. */
export function EditCard({ edit, children }: { edit: Edit; children?: ReactNode }) {
  const shownFilm = edit.proposed_film ?? edit.replaced_film;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Poster uri={shownFilm?.poster_url ?? null} width={FILM_ROW_POSTER_WIDTH} />
        <View style={styles.headerText}>
          <ThemedText type="small" themeColor="textSecondary">
            Suggestions for {edit.film.title}
            {edit.film.year ? ` (${edit.film.year})` : ''}
          </ThemedText>
          <ThemedText type="smallBold">{describeEdit(edit)}</ThemedText>
          {edit.proposer && (
            <ThemedText type="small" themeColor="textSecondary">
              by {edit.proposer}
            </ThemedText>
          )}
        </View>
      </View>
      {edit.audio_url ? (
        <AudioExplanation uri={edit.audio_url} durationMs={edit.audio_duration_ms ?? null} />
      ) : edit.explanation ? (
        <ThemedText type="small">{edit.explanation}</ThemedText>
      ) : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: Spacing.two, padding: Spacing.three },
  header: { flexDirection: 'row', gap: Spacing.three },
  headerText: { flex: 1, gap: Spacing.half },
});
