import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { describeError } from '@/api/client';
import { type EditAction, useProposeEdit } from '@/api/edits';
import {
  type FilmDetail,
  type FilmSearchResult,
  MIN_SEARCH_LENGTH,
  useFilm,
  useFilmSearch,
} from '@/api/films';
import { AudioRecorder } from '@/components/audio-recorder';
import { Button } from '@/components/button';
import { FilmRow } from '@/components/film-row';
import { Message } from '@/components/message';
import { ThemedText } from '@/components/themed-text';
import { EXPLANATION_MAX_CHARS, VOTES_REQUIRED } from '@/constants/limits';
import { Spacing } from '@/constants/theme';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useTheme } from '@/hooks/use-theme';

type Params = {
  /** The film whose suggestions are being changed. */
  tmdbId: string;
  action: EditAction;
  /** The suggested film being replaced (replace only). */
  replaced?: string;
  /** Replace the film with itself, i.e. just update its explanation. */
  keepFilm?: string;
};

/** Propose adding a suggestion, or replacing one (possibly with itself, to update its explanation). */
export default function ProposeScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<Params>();
  const film = useFilm(Number(params.tmdbId));

  return (
    <>
      <Stack.Screen
        options={{
          headerLeft: () => (
            <Pressable onPress={() => router.back()} hitSlop={8}>
              <ThemedText themeColor="tint">Cancel</ThemedText>
            </Pressable>
          ),
        }}
      />
      {film.isPending ? (
        <Message loading />
      ) : film.isError ? (
        <Message title="Couldn’t load this film" body={describeError(film.error)} />
      ) : (
        <ProposeForm
          film={film.data}
          action={params.action}
          replaced={params.replaced ? Number(params.replaced) : undefined}
          keepFilm={Boolean(params.keepFilm)}
        />
      )}
    </>
  );
}

type FormProps = {
  film: FilmDetail;
  action: EditAction;
  replaced?: number;
  keepFilm: boolean;
};

function ProposeForm({ film, action, replaced, keepFilm }: FormProps) {
  const theme = useTheme();
  const router = useRouter();
  const proposeEdit = useProposeEdit(film.tmdb_id);
  const replacedSuggestion = film.suggestions.find((s) => s.film.tmdb_id === replaced);

  const [chosen, setChosen] = useState<FilmSearchResult | null>(
    keepFilm && replacedSuggestion ? { ...replacedSuggestion.film, matched_title: null } : null,
  );
  const [mode, setMode] = useState<'write' | 'record'>('write');
  const [text, setText] = useState(keepFilm ? (replacedSuggestion?.explanation ?? '') : '');
  const [audioUri, setAudioUri] = useState<string | null>(null);

  if (action !== 'add' && !replacedSuggestion) {
    return <Message title="That suggestion has changed" body="Go back and try again." />;
  }

  const title =
    action === 'add'
      ? 'Suggest a film'
      : keepFilm
        ? 'Update explanation'
        : `Replace ${replacedSuggestion?.film.title}`;
  const tooLong = text.length > EXPLANATION_MAX_CHARS;
  const hasExplanation = mode === 'write' ? text.trim().length > 0 && !tooLong : audioUri !== null;

  function submit() {
    if (!chosen) return;
    proposeEdit.mutate(
      {
        action,
        proposedFilm: chosen.tmdb_id,
        replacedFilm: replaced,
        ...(mode === 'write' ? { explanation: text.trim() } : { audioUri: audioUri ?? undefined }),
      },
      {
        onSuccess: (edit) => {
          if (edit.status === 'pending') {
            Alert.alert(
              'Sent for review',
              `It goes live once ${VOTES_REQUIRED} other people approve it.`,
            );
          }
          router.back();
        },
      },
    );
  }

  return (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      contentContainerStyle={styles.content}>
      <Stack.Screen options={{ title }} />
      <ThemedText type="small" themeColor="textSecondary">
        For people who just watched {film.title}
        {film.year ? ` (${film.year})` : ''}
      </ThemedText>

      {chosen ? (
        <View>
          <View style={styles.bleed}>
            <FilmRow film={chosen} onPress={() => {}} />
          </View>
          {!keepFilm && (
            <Button title="Choose a different film" variant="plain" onPress={() => setChosen(null)} />
          )}
        </View>
      ) : (
        <FilmPicker
          exclude={[film.tmdb_id, ...film.suggestions.map((s) => s.film.tmdb_id)]}
          onChoose={setChosen}
        />
      )}

      {chosen && (
        <View style={styles.section}>
          <ThemedText type="smallBold">Why should they watch it next?</ThemedText>
          <View style={styles.modes}>
            <Button
              title="Write"
              variant={mode === 'write' ? 'selected' : 'plain'}
              onPress={() => setMode('write')}
            />
            <Button
              title="Record"
              variant={mode === 'record' ? 'selected' : 'plain'}
              onPress={() => setMode('record')}
            />
          </View>
          {mode === 'write' ? (
            <>
              <TextInput
                value={text}
                onChangeText={setText}
                multiline
                placeholder="What do the two films share?"
                placeholderTextColor={theme.textSecondary}
                style={[
                  styles.textArea,
                  { color: theme.text, backgroundColor: theme.backgroundElement },
                ]}
              />
              <ThemedText
                type="small"
                themeColor="textSecondary"
                style={[styles.counter, tooLong && styles.error]}>
                {text.length} / {EXPLANATION_MAX_CHARS}
              </ThemedText>
            </>
          ) : (
            <AudioRecorder uri={audioUri} onChange={setAudioUri} />
          )}
        </View>
      )}

      {proposeEdit.error && (
        <ThemedText type="small" style={styles.error}>
          {describeError(proposeEdit.error)}
        </ThemedText>
      )}
      {chosen && (
        <Button
          title={action === 'add' ? 'Add suggestion' : 'Send for review'}
          disabled={!hasExplanation}
          loading={proposeEdit.isPending}
          onPress={submit}
        />
      )}
    </ScrollView>
  );
}

function FilmPicker({
  exclude,
  onChoose,
}: {
  exclude: number[];
  onChoose: (film: FilmSearchResult) => void;
}) {
  const theme = useTheme();
  const [query, setQuery] = useState('');
  const debounced = useDebouncedValue(query.trim(), 250);
  const search = useFilmSearch(debounced);
  const searching = debounced.length >= MIN_SEARCH_LENGTH;
  const results = (search.data ?? []).filter((film) => !exclude.includes(film.tmdb_id));

  return (
    <View style={styles.section}>
      <TextInput
        value={query}
        onChangeText={setQuery}
        autoFocus
        autoCorrect={false}
        clearButtonMode="while-editing"
        placeholder="Search for the film to suggest"
        placeholderTextColor={theme.textSecondary}
        style={[styles.input, { color: theme.text, backgroundColor: theme.backgroundElement }]}
      />
      {searching && search.isPending && <Message loading />}
      {searching && search.isSuccess && results.length === 0 && (
        <Message title={`No films found for “${debounced}”`} />
      )}
      {searching && (
        <View style={styles.bleed}>
          {results.map((film) => (
            <FilmRow key={film.tmdb_id} film={film} onPress={onChoose} />
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.three, gap: Spacing.three },
  section: { gap: Spacing.two },
  // Film rows have their own side padding.
  bleed: { marginHorizontal: -Spacing.three },
  modes: { flexDirection: 'row', gap: Spacing.two },
  input: {
    fontSize: 16,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two + Spacing.one,
    borderRadius: 10,
  },
  textArea: {
    fontSize: 16,
    minHeight: 120,
    padding: Spacing.three,
    borderRadius: 10,
    textAlignVertical: 'top',
  },
  counter: { alignSelf: 'flex-end' },
  error: { color: '#DC2626' },
});
