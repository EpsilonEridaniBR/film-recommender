import { useMutation, useQuery } from '@tanstack/react-query';

import { api, unwrap } from './client';
import type { components } from './schema';
import { signIn, useSignedIn } from './session';

export type Me = components['schemas']['Me'];

/**
 * Queries whose answers depend on who's signed in start with this key, so
 * they're thrown away when someone signs in or out (see _layout.tsx).
 */
export const USER_QUERY_KEY = 'user';

export function useMe() {
  const signedIn = useSignedIn();
  return useQuery({
    queryKey: [USER_QUERY_KEY, 'me'],
    queryFn: async ({ signal }) => unwrap(await api.GET('/api/v1/me/', { signal })),
    enabled: signedIn,
  });
}

/** Development only: sign in with just a display name (the server must have DEBUG on). */
export function useDevSignIn() {
  return useMutation({
    mutationFn: async (displayName: string) =>
      unwrap(await api.POST('/api/v1/auth/dev/', { body: { display_name: displayName } })),
    onSuccess: ({ access, refresh }) => signIn({ access, refresh }),
  });
}
