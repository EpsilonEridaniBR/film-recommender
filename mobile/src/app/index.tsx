import { Link, Stack } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useState } from 'react';
import { FlatList, Pressable, StyleSheet, View } from 'react-native';

import { MIN_SEARCH_LENGTH, useFilmSearch } from '@/api/films';
import { FILM_ROW_POSTER_WIDTH, FilmRow } from '@/components/film-row';
import { Message } from '@/components/message';
import { Spacing } from '@/constants/theme';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useTheme } from '@/hooks/use-theme';

export default function SearchScreen() {
  const theme = useTheme();
  const [query, setQuery] = useState('');
  const debounced = useDebouncedValue(query.trim(), 250);
  const search = useFilmSearch(debounced);
  const searching = debounced.length >= MIN_SEARCH_LENGTH;

  function emptyState() {
    if (!searching) {
      return (
        <Message
          title="What did you just watch?"
          body="Search for it and we'll suggest what to watch next."
        />
      );
    }
    if (search.isPending) return <Message loading />;
    if (search.isError) {
      return <Message title="Couldn't reach the server" body="Check your connection and try again." />;
    }
    return <Message title={`No films found for “${debounced}”`} />;
  }

  return (
    <>
      <Stack.Screen
        options={{
          headerSearchBarOptions: {
            placeholder: 'Search films',
            autoCapitalize: 'none',
            hideWhenScrolling: false,
            onChangeText: (event) => setQuery(event.nativeEvent.text),
          },
          headerRight: () => (
            <View style={styles.headerButtons}>
              <Link href="/about" asChild>
                <Pressable accessibilityLabel="About" hitSlop={8}>
                  <SymbolView name="info.circle" size={22} tintColor={theme.tint} />
                </Pressable>
              </Link>
              <Link href="/account" asChild>
                <Pressable accessibilityLabel="Account" hitSlop={8}>
                  <SymbolView name="person.crop.circle" size={22} tintColor={theme.tint} />
                </Pressable>
              </Link>
            </View>
          ),
        }}
      />
      <FlatList
        contentInsetAdjustmentBehavior="automatic"
        keyboardDismissMode="on-drag"
        keyboardShouldPersistTaps="handled"
        data={searching ? (search.data ?? []) : []}
        keyExtractor={(film) => String(film.tmdb_id)}
        renderItem={({ item }) => <FilmRow film={item} />}
        ItemSeparatorComponent={() => (
          <View style={[styles.separator, { backgroundColor: theme.border }]} />
        )}
        ListEmptyComponent={emptyState()}
      />
    </>
  );
}

const styles = StyleSheet.create({
  headerButtons: { flexDirection: 'row', gap: Spacing.three },
  separator: {
    height: StyleSheet.hairlineWidth,
    // Start under the titles rather than under the posters.
    marginLeft: Spacing.three + FILM_ROW_POSTER_WIDTH + Spacing.three,
  },
});
