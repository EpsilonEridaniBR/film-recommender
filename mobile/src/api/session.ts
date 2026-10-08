import * as SecureStore from 'expo-secure-store';
import { useSyncExternalStore } from 'react';

import { API_URL } from './config';

/** The signed-in user's API tokens, kept in the keychain between launches. */
type Tokens = { access: string; refresh: string };

const STORAGE_KEY = 'session';
// Refresh the access token when it has less than this long left.
const REFRESH_MARGIN_MS = 60 * 1000;

let tokens = readStoredTokens();
let refreshing: Promise<void> | null = null;
const listeners = new Set<() => void>();

function readStoredTokens(): Tokens | null {
  try {
    const stored = SecureStore.getItem(STORAGE_KEY);
    return stored ? (JSON.parse(stored) as Tokens) : null;
  } catch {
    return null;
  }
}

function setTokens(next: Tokens | null) {
  tokens = next;
  if (next) {
    SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(next));
  } else {
    SecureStore.deleteItemAsync(STORAGE_KEY);
  }
  listeners.forEach((listener) => listener());
}

export function signIn(next: Tokens) {
  setTokens(next);
}

export function signOut() {
  if (tokens) setTokens(null);
}

/** Call `listener` whenever someone signs in or out. Returns an unsubscribe function. */
export function onSessionChange(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSignedIn() {
  return useSyncExternalStore(onSessionChange, () => tokens !== null);
}

/** When a JWT expires, in milliseconds since the epoch (0 if it can't be read). */
function expiresAt(jwt: string) {
  try {
    const payload = jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payload + '='.repeat((4 - (payload.length % 4)) % 4);
    return (JSON.parse(atob(padded)).exp as number) * 1000;
  } catch {
    return 0;
  }
}

async function refresh() {
  const current = tokens;
  if (!current) return;
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: current.refresh }),
    });
  } catch {
    return; // Offline: keep the tokens and let the request fail on its own.
  }
  // Someone may have signed out (or in as someone else) meanwhile.
  if (tokens !== current) return;
  if (!response.ok) {
    signOut(); // The refresh token has expired or been revoked.
    return;
  }
  const data = (await response.json()) as Tokens;
  setTokens({ access: data.access, refresh: data.refresh ?? current.refresh });
}

/**
 * The access token to send, refreshed first if it's about to expire. Refreshing
 * before the request (rather than retrying after a 401) means uploads never
 * need sending twice.
 */
export async function accessToken() {
  if (tokens && expiresAt(tokens.access) - Date.now() < REFRESH_MARGIN_MS) {
    refreshing ??= refresh().finally(() => {
      refreshing = null;
    });
    await refreshing;
  }
  return tokens?.access ?? null;
}
