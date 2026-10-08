import { ScrollView, StyleSheet } from 'react-native';

import { ExternalLink } from '@/components/external-link';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

export default function AboutScreen() {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <ThemedText>
        Search for a film you’ve just watched and get hand-picked suggestions for what to
        watch next, each with a reason from someone who’s seen both.
      </ThemedText>
      <ThemedText type="smallBold">Film data</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        This product uses the TMDB API but is not endorsed or certified by TMDB. Film
        titles, descriptions and posters come from The Movie Database.
      </ThemedText>
      <ExternalLink href="https://www.themoviedb.org">
        <ThemedText type="linkPrimary">themoviedb.org</ThemedText>
      </ExternalLink>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.four, gap: Spacing.three },
});
