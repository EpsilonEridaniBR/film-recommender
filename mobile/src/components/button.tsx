import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Props = {
  title: string;
  onPress: () => void;
  /** filled: the main action. plain: a secondary one. selected: a chosen option. */
  variant?: 'filled' | 'plain' | 'selected';
  disabled?: boolean;
  loading?: boolean;
  destructive?: boolean;
};

export function Button({
  title,
  onPress,
  variant = 'filled',
  disabled = false,
  loading = false,
  destructive = false,
}: Props) {
  const theme = useTheme();
  const accent = destructive ? '#DC2626' : theme.tint;
  const background =
    variant === 'filled' ? accent : variant === 'selected' ? theme.backgroundSelected : theme.backgroundElement;
  const color = variant === 'filled' ? '#ffffff' : variant === 'selected' ? theme.text : accent;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading, selected: variant === 'selected' }}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background },
        (pressed || disabled) && styles.dimmed,
      ]}>
      {loading ? (
        <ActivityIndicator color={color} />
      ) : (
        <ThemedText type="smallBold" style={{ color }}>
          {title}
        </ThemedText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 10,
  },
  dimmed: { opacity: 0.5 },
});
