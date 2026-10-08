import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Fragment } from 'react';
import { ActionSheetIOS, Alert, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError, describeError } from '@/api/client';
import { type EditAction, useProposeEdit } from '@/api/edits';
import { type FilmDetail, type Suggestion, useFilm } from '@/api/films';
import { useSignedIn } from '@/api/session';
import { Button } from '@/components/button';
import { FilmHeading } from '@/components/film-heading';
import { Message } from '@/components/message';
import { LARGE_POSTER_WIDTH, Poster } from '@/components/poster';
import { SuggestionCard } from '@/components/suggestion-card';
import { ThemedText } from '@/components/themed-text';
import { VOTES_REQUIRED } from '@/constants/limits';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function FilmScreen() {
  const theme = useTheme();
  const { tmdbId } = useLocalSearchParams<{ tmdbId: string }>();
  const film = useFilm(Number(tmdbId));

  return (
    <>
      {/* Just a back chevron: the title is already shown next to the poster. */}
      <Stack.Screen
        options={{
          title: '',
          headerShadowVisible: false,
          headerStyle: { backgroundColor: theme.background },
        }}
      />
      <ScrollView contentInsetAdjustmentBehavior="automatic">
        {film.isPending ? (
          <Message loading />
        ) : film.isError ? (
          <Message
            title={
              film.error instanceof ApiError && film.error.status === 404
                ? 'Film not found'
                : "Couldn't load this film"
            }
          />
        ) : (
          <FilmContent film={film.data} />
        )}
      </ScrollView>
    </>
  );
}

function FilmContent({ film }: { film: FilmDetail }) {
  const theme = useTheme();
  const router = useRouter();
  const signedIn = useSignedIn();
  const proposeEdit = useProposeEdit(film.tmdb_id);
  const canAdd = film.suggestions.length < film.max_suggestions;

  function propose(params: { action: EditAction; replaced?: number; keepFilm?: boolean }) {
    if (!signedIn) {
      router.push('/account');
      return;
    }
    router.push({
      pathname: '/propose',
      params: {
        tmdbId: film.tmdb_id,
        action: params.action,
        ...(params.replaced && { replaced: params.replaced }),
        ...(params.keepFilm && { keepFilm: 1 }),
      },
    });
  }

  function confirmRemove(suggestion: Suggestion) {
    Alert.alert(
      `Remove ${suggestion.film.title}?`,
      `This goes to the review queue and needs ${VOTES_REQUIRED} approvals.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () =>
            proposeEdit.mutate(
              { action: 'remove', replacedFilm: suggestion.film.tmdb_id },
              {
                onSuccess: () => Alert.alert('Sent for review'),
                onError: (error) => Alert.alert('Couldn’t propose that', describeError(error)),
              },
            ),
        },
      ],
    );
  }

  function showActions(suggestion: Suggestion) {
    if (!signedIn) {
      router.push('/account');
      return;
    }
    const replaced = suggestion.film.tmdb_id;
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title: suggestion.film.title,
        options: ['Update explanation', 'Replace with another film', 'Remove', 'Cancel'],
        destructiveButtonIndex: 2,
        cancelButtonIndex: 3,
      },
      (index) => {
        if (index === 0) propose({ action: 'replace', replaced, keepFilm: true });
        if (index === 1) propose({ action: 'replace', replaced });
        if (index === 2) confirmRemove(suggestion);
      },
    );
  }

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <Poster uri={film.poster_url} width={LARGE_POSTER_WIDTH / 1.5} />
        <View style={styles.headerText}>
          <FilmHeading
            title={film.title}
            originalTitle={film.original_title}
            year={film.year}
            runtime={film.runtime}
            directors={film.directors.map((d) => d.name)}
            topCast={film.top_cast ?? []}
            titleSize={22}
            showOriginalTitle={false}
          />
        </View>
      </View>

      <View style={[styles.divider, { backgroundColor: theme.border }]} />

      <ThemedText type="smallBold" style={styles.sectionTitle}>
        Watch next
      </ThemedText>
      {film.suggestions.length > 0 ? (
        <View>
          {film.suggestions.map((suggestion, index) => (
            <Fragment key={suggestion.id}>
              {index > 0 && (
                <View style={[styles.suggestionDivider, { backgroundColor: theme.border }]} />
              )}
              <SuggestionCard suggestion={suggestion} onMore={() => showActions(suggestion)} />
            </Fragment>
          ))}
        </View>
      ) : (
        <Message body="No suggestions for this film yet." />
      )}
      {canAdd && (
        <Button title="Suggest a film" variant="plain" onPress={() => propose({ action: 'add' })} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.three, gap: Spacing.three },
  header: { flexDirection: 'row', gap: Spacing.three },
  headerText: { flex: 1 },
  divider: { height: StyleSheet.hairlineWidth, marginVertical: Spacing.two },
  sectionTitle: { fontSize: 18 },
  suggestionDivider: { height: StyleSheet.hairlineWidth },
});
