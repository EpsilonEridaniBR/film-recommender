import Constants from 'expo-constants';

/**
 * Where the Django API lives.
 *
 * Set EXPO_PUBLIC_API_URL for deployed builds. In development it defaults to
 * port 8000 on the machine running Metro, so the phone reaches Django over
 * the local network (run Django with `runserver 0.0.0.0:8000`).
 */
function developmentApiUrl() {
  const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
  return `http://${host}:8000`;
}

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? developmentApiUrl();
