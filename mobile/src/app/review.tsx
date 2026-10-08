import { Alert, FlatList, StyleSheet, View } from 'react-native';

import { describeError } from '@/api/client';
import { type Edit, useReviewQueue, useVote } from '@/api/edits';
import { Button } from '@/components/button';
import { EditCard } from '@/components/edit-card';
import { Message } from '@/components/message';
import { ThemedText } from '@/components/themed-text';
import { VOTES_REQUIRED } from '@/constants/limits';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** Pending edits for moderators to approve or reject. */
export default function ReviewScreen() {
  const theme = useTheme();
  const queue = useReviewQueue();

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic"
      data={queue.data?.results ?? []}
      keyExtractor={(edit) => String(edit.id)}
      renderItem={({ item }) => <ReviewItem edit={item} />}
      ItemSeparatorComponent={() => (
        <View style={[styles.separator, { backgroundColor: theme.border }]} />
      )}
      refreshing={queue.isRefetching}
      onRefresh={() => queue.refetch()}
      ListEmptyComponent={
        queue.isPending ? (
          <Message loading />
        ) : queue.isError ? (
          <Message title="Couldn’t load the queue" body={describeError(queue.error)} />
        ) : (
          <Message title="Nothing to review" body="Every proposed change has been settled." />
        )
      }
    />
  );
}

function ReviewItem({ edit }: { edit: Edit }) {
  const vote = useVote();

  function castVote(approve: boolean) {
    vote.mutate(
      { editId: edit.id, approve },
      { onError: (error) => Alert.alert('Couldn’t record your vote', describeError(error)) },
    );
  }

  return (
    <EditCard edit={edit}>
      <ThemedText type="small" themeColor="textSecondary">
        {edit.approvals} of {VOTES_REQUIRED} approvals · {edit.rejections} of {VOTES_REQUIRED}{' '}
        rejections
      </ThemedText>
      {edit.is_mine ? (
        <ThemedText type="small" themeColor="textSecondary">
          Your edit: others will review it.
        </ThemedText>
      ) : (
        <View style={styles.buttons}>
          <View style={styles.button}>
            <Button
              title={edit.my_vote === true ? 'Approved' : 'Approve'}
              variant={edit.my_vote === true ? 'selected' : 'plain'}
              disabled={vote.isPending}
              onPress={() => castVote(true)}
            />
          </View>
          <View style={styles.button}>
            <Button
              title={edit.my_vote === false ? 'Rejected' : 'Reject'}
              variant={edit.my_vote === false ? 'selected' : 'plain'}
              destructive
              disabled={vote.isPending}
              onPress={() => castVote(false)}
            />
          </View>
        </View>
      )}
    </EditCard>
  );
}

const styles = StyleSheet.create({
  separator: { height: StyleSheet.hairlineWidth, marginLeft: Spacing.three },
  buttons: { flexDirection: 'row', gap: Spacing.two },
  button: { flex: 1 },
});
