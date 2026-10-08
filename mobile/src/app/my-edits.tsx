import { Alert, FlatList, StyleSheet, View } from 'react-native';

import { describeError } from '@/api/client';
import { type Edit, useMyEdits, useWithdrawEdit } from '@/api/edits';
import { Button } from '@/components/button';
import { EditCard } from '@/components/edit-card';
import { Message } from '@/components/message';
import { ThemedText } from '@/components/themed-text';
import { VOTES_REQUIRED } from '@/constants/limits';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

function statusLabel(edit: Edit) {
  switch (edit.status) {
    case 'pending':
      return `Waiting for review: ${edit.approvals} of ${VOTES_REQUIRED} approvals`;
    case 'approved':
      return 'Approved';
    case 'auto_approved':
      return 'Added';
    case 'rejected':
      return edit.note ? `Rejected: ${edit.note}` : 'Rejected';
    case 'withdrawn':
      return 'Withdrawn';
    default:
      return edit.status;
  }
}

/** The signed-in user's edits, newest first, with a way to withdraw pending ones. */
export default function MyEditsScreen() {
  const theme = useTheme();
  const edits = useMyEdits();

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic"
      data={edits.data?.results ?? []}
      keyExtractor={(edit) => String(edit.id)}
      renderItem={({ item }) => <MyEdit edit={item} />}
      ItemSeparatorComponent={() => (
        <View style={[styles.separator, { backgroundColor: theme.border }]} />
      )}
      refreshing={edits.isRefetching}
      onRefresh={() => edits.refetch()}
      ListEmptyComponent={
        edits.isPending ? (
          <Message loading />
        ) : edits.isError ? (
          <Message title="Couldn’t load your edits" body={describeError(edits.error)} />
        ) : (
          <Message
            title="No edits yet"
            body="Open a film and suggest what to watch next, or change one of its suggestions."
          />
        )
      }
    />
  );
}

function MyEdit({ edit }: { edit: Edit }) {
  const withdraw = useWithdrawEdit();

  function confirmWithdraw() {
    Alert.alert('Withdraw this edit?', undefined, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Withdraw',
        style: 'destructive',
        onPress: () =>
          withdraw.mutate(edit.id, {
            onError: (error) => Alert.alert('Couldn’t withdraw it', describeError(error)),
          }),
      },
    ]);
  }

  return (
    <EditCard edit={edit}>
      <ThemedText type="smallBold" themeColor={edit.status === 'pending' ? 'tint' : 'textSecondary'}>
        {statusLabel(edit)}
      </ThemedText>
      {edit.status === 'pending' && (
        <Button
          title="Withdraw"
          variant="plain"
          destructive
          loading={withdraw.isPending}
          onPress={confirmWithdraw}
        />
      )}
    </EditCard>
  );
}

const styles = StyleSheet.create({
  separator: { height: StyleSheet.hairlineWidth, marginLeft: Spacing.three },
});
