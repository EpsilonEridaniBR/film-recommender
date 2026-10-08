import { Image } from 'expo-image';
import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/hooks/use-theme';

/** Poster width for the film page and its suggestion cards. */
export const LARGE_POSTER_WIDTH = 120;

type Props = { uri: string | null; width: number };

/** A film poster at the standard 2:3 ratio, with a placeholder when TMDB has none. */
export function Poster({ uri, width }: Props) {
  const theme = useTheme();
  const size = { width, height: width * 1.5 };
  if (!uri) {
    return <View style={[styles.poster, size, { backgroundColor: theme.backgroundSelected }]} />;
  }
  return <Image source={{ uri }} style={[styles.poster, size]} contentFit="cover" transition={150} />;
}

const styles = StyleSheet.create({
  poster: { borderRadius: 6 },
});
