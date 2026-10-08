import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

/** Centred text for empty, loading and error states. */
export function Message({ title, body, loading }: { title?: string; body?: string; loading?: boolean }) {
  return (
    <View style={styles.container}>
      {loading && <ActivityIndicator />}
      {title && <ThemedText style={styles.center}>{title}</ThemedText>}
      {body && (
        <ThemedText type="small" themeColor="textSecondary" style={styles.center}>
          {body}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: Spacing.five, gap: Spacing.two, alignItems: 'center' },
  center: { textAlign: 'center' },
});
