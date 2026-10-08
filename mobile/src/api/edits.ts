import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { File } from 'expo-file-system';

import { USER_QUERY_KEY } from './account';
import { api, unwrap } from './client';
import type { components } from './schema';

export type Edit = components['schemas']['Edit'];
export type EditAction = components['schemas']['ActionEnum'];

export type Proposal = {
  action: EditAction;
  /** TMDB id of the film to suggest (add/replace). */
  proposedFilm?: number;
  /** TMDB id of the suggested film to take out (replace/remove). */
  replacedFilm?: number;
  explanation?: string;
  /** A local recording, sent instead of `explanation`. */
  audioUri?: string;
};

/** After any change: suggestions, queues and the pending count may all be different. */
function refreshAfterEdit(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ['films', 'detail'] });
  queryClient.invalidateQueries({ queryKey: [USER_QUERY_KEY] });
}

export function useProposeEdit(tmdbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ action, proposedFilm, replacedFilm, explanation, audioUri }: Proposal) => {
      const body = {
        action,
        proposed_film: proposedFilm,
        replaced_film: replacedFilm,
        explanation: audioUri ? undefined : explanation,
      };
      const params = { path: { tmdb_id: tmdbId } };
      if (!audioUri) {
        return unwrap(await api.POST('/api/v1/films/{tmdb_id}/edits/', { params, body }));
      }
      const form = new FormData();
      for (const [key, value] of Object.entries(body)) {
        if (value !== undefined) form.append(key, String(value));
      }
      // Expo's fetch reads the recording's bytes from an expo-file-system File;
      // React Native's {uri, name, type} shape isn't supported by it.
      form.append('audio', new File(audioUri));
      return unwrap(
        await api.POST('/api/v1/films/{tmdb_id}/edits/', {
          params,
          body,
          bodySerializer: () => form,
        }),
      );
    },
    onSuccess: () => refreshAfterEdit(queryClient),
  });
}

/** Edits waiting for votes, oldest first. */
export function useReviewQueue() {
  return useQuery({
    queryKey: [USER_QUERY_KEY, 'edits', 'queue'],
    queryFn: async ({ signal }) =>
      unwrap(await api.GET('/api/v1/edits/', { params: { query: { status: 'pending' } }, signal })),
  });
}

/** Your own edits, newest first. */
export function useMyEdits() {
  return useQuery({
    queryKey: [USER_QUERY_KEY, 'edits', 'mine'],
    queryFn: async ({ signal }) => unwrap(await api.GET('/api/v1/me/edits/', { signal })),
  });
}

export function useVote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ editId, approve }: { editId: number; approve: boolean }) =>
      unwrap(
        await api.POST('/api/v1/edits/{id}/vote/', {
          params: { path: { id: editId } },
          body: { approve },
        }),
      ),
    onSuccess: () => refreshAfterEdit(queryClient),
  });
}

export function useWithdrawEdit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (editId: number) =>
      unwrap(await api.DELETE('/api/v1/edits/{id}/', { params: { path: { id: editId } } })),
    onSuccess: () => refreshAfterEdit(queryClient),
  });
}
