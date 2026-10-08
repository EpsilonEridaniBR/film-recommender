import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { formatRuntime } from '@/utils/format';

type Props = {
  title: string;
  originalTitle: string;
  year: number | null;
  runtime?: number | null;
  directors: string[];
  topCast?: string[];
  titleSize?: number;
  showOriginalTitle?: boolean;
};

/**
 * **Title** year
 * *Original title* (only when different, and if shown)
 * Director · runtime
 * Top actors
 */
export function FilmHeading({
  title,
  originalTitle,
  year,
  runtime,
  directors,
  topCast = [],
  titleSize = 16,
  showOriginalTitle = true,
}: Props) {
  const directorAndRuntime = [directors.join(', '), formatRuntime(runtime)]
    .filter(Boolean)
    .join(' · ');

  return (
    <View style={styles.container}>
      <ThemedText type="smallBold" style={{ fontSize: titleSize, lineHeight: titleSize * 1.3 }}>
        {title}
        {year ? (
          <ThemedText type="small" themeColor="textSecondary" style={styles.regular}>
            {'  '}
            {year}
          </ThemedText>
        ) : null}
      </ThemedText>
      {showOriginalTitle && originalTitle && originalTitle !== title ? (
        <ThemedText themeColor="textSecondary" style={styles.italic}>
          {originalTitle}
        </ThemedText>
      ) : null}
      {directorAndRuntime ? (
        <ThemedText themeColor="textSecondary">{directorAndRuntime}</ThemedText>
      ) : null}
      {topCast.length > 0 ? (
        <ThemedText themeColor="textSecondary" style={styles.regular}>
          {topCast.join(', ')}
        </ThemedText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: Spacing.half },
  italic: { fontStyle: 'italic', fontWeight: 400 },
  regular: { fontWeight: 400 },
});
