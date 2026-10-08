import { getLocales } from 'expo-localization';
import createClient, { type Middleware } from 'openapi-fetch';

import { API_URL } from './config';
import type { paths } from './schema';
import { accessToken, signOut } from './session';

/** The phone's language; the API returns titles in it (falling back to English). */
export function appLanguage() {
  return getLocales()[0]?.languageCode ?? 'en';
}

const sendLanguage: Middleware = {
  onRequest({ request }) {
    request.headers.set('Accept-Language', appLanguage());
    return request;
  },
};

const sendToken: Middleware = {
  async onRequest({ request }) {
    const token = await accessToken();
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    return request;
  },
  onResponse({ request, response }) {
    // The account was deleted or disabled, or its tokens revoked.
    if (response.status === 401 && request.headers.has('Authorization')) signOut();
    // Return nothing: returning `response` fails openapi-fetch's
    // `instanceof Response` check in React Native.
  },
};

export const api = createClient<paths>({ baseUrl: API_URL });
api.use(sendLanguage, sendToken);

export class ApiError extends Error {
  constructor(
    public status: number,
    message?: string,
  ) {
    super(message ?? `API request failed (${status})`);
  }
}

/** The server's explanation of an error: `detail`, or the first field error. */
function errorMessage(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return undefined;
  if ('detail' in error && typeof error.detail === 'string') return error.detail;
  const first: unknown = Object.values(error)[0];
  if (typeof first === 'string') return first;
  if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
  return undefined;
}

/** Unwrap an openapi-fetch result, throwing on errors so React Query sees them. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw new ApiError(result.response.status, errorMessage(result.error));
  }
  return result.data;
}

/** A message to show for a failed request. */
export function describeError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  const message = 'Couldn’t reach the server. Check your connection and try again.';
  // In development, show what actually went wrong rather than guessing.
  return __DEV__ && error instanceof Error ? `${message} (${error.message})` : message;
}
