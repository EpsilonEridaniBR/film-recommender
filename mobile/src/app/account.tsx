import { useRouter } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { useDevSignIn, useMe } from '@/api/account';
import { ApiError, describeError } from '@/api/client';
import { signOut, useSignedIn } from '@/api/session';
import { Button } from '@/components/button';
import { Message } from '@/components/message';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function AccountScreen() {
  const signedIn = useSignedIn();
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={styles.content}>
      {signedIn ? <SignedIn /> : <SignedOut />}
    </ScrollView>
  );
}

function SignedIn() {
  const router = useRouter();
  const me = useMe();

  if (me.isPending) return <Message loading />;
  if (me.isError) return <Message title="Couldn’t load your account" body={describeError(me.error)} />;

  return (
    <>
      <View style={styles.section}>
        <ThemedText type="small" themeColor="textSecondary">
          Signed in as
        </ThemedText>
        <ThemedText style={styles.name}>{me.data.display_name}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          Edits waiting for review: {me.data.pending_edits} of {me.data.max_pending_edits}
        </ThemedText>
      </View>
      <View>
        <LinkRow title="Review queue" icon="checkmark.circle" onPress={() => router.push('/review')} />
        <LinkRow title="My edits" icon="pencil" onPress={() => router.push('/my-edits')} />
      </View>
      <Button title="Sign out" variant="plain" destructive onPress={signOut} />
    </>
  );
}

function LinkRow({
  title,
  icon,
  onPress,
}: {
  title: string;
  icon: 'checkmark.circle' | 'pencil';
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.linkRow,
        { borderBottomColor: theme.border },
        pressed && styles.pressed,
      ]}>
      <SymbolView name={icon} size={20} tintColor={theme.tint} />
      <ThemedText style={styles.linkTitle}>{title}</ThemedText>
      <SymbolView name="chevron.right" size={14} tintColor={theme.textSecondary} />
    </Pressable>
  );
}

// Quick picks for switching between test users (proposers can't vote on their own edits).
const TEST_USERS = ['Alice', 'Bob', 'Carol'];

function SignedOut() {
  const theme = useTheme();
  const [name, setName] = useState('');
  const devSignIn = useDevSignIn();

  const error =
    devSignIn.error instanceof ApiError && devSignIn.error.status === 404
      ? 'Developer sign-in is off on the server. Run Django with DEBUG=True.'
      : devSignIn.error
        ? describeError(devSignIn.error)
        : null;

  return (
    <>
      <ThemedText>Sign in to suggest films and review other people’s changes.</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        Sign in with Apple is coming soon.
      </ThemedText>

      {__DEV__ && (
        <View style={styles.section}>
          <ThemedText type="smallBold">Developer sign in</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            Development only: sign in as anyone by typing a name. The same name always gives the
            same account.
          </ThemedText>
          <View style={styles.chips}>
            {TEST_USERS.map((user) => (
              <Button
                key={user}
                title={user}
                variant="plain"
                disabled={devSignIn.isPending}
                onPress={() => devSignIn.mutate(user)}
              />
            ))}
          </View>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Or type a name"
            placeholderTextColor={theme.textSecondary}
            autoCorrect={false}
            returnKeyType="go"
            onSubmitEditing={() => name.trim() && devSignIn.mutate(name)}
            style={[styles.input, { color: theme.text, backgroundColor: theme.backgroundElement }]}
          />
          <Button
            title="Sign in"
            disabled={!name.trim()}
            loading={devSignIn.isPending}
            onPress={() => devSignIn.mutate(name)}
          />
          {error && (
            <ThemedText type="small" style={styles.error}>
              {error}
            </ThemedText>
          )}
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.three, gap: Spacing.four },
  section: { gap: Spacing.two },
  name: { fontSize: 22, lineHeight: 28, fontWeight: 700 },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  linkTitle: { flex: 1 },
  pressed: { opacity: 0.6 },
  chips: { flexDirection: 'row', gap: Spacing.two },
  input: {
    fontSize: 16,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two + Spacing.one,
    borderRadius: 10,
  },
  error: { color: '#DC2626' },
});
