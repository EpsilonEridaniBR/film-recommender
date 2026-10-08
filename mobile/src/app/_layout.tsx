import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setAudioModeAsync } from 'expo-audio';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';

import { USER_QUERY_KEY } from '@/api/account';
import { onSessionChange } from '@/api/session';

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 5 * 60 * 1000, retry: 1 } },
      }),
  );

  useEffect(() => {
    // Let explanations play even when the phone's silent switch is on.
    setAudioModeAsync({ playsInSilentMode: true });
  }, []);

  // Profile, queue and votes belong to whoever was signed in: refetch them
  // for the new user (or clear them) on sign-in and sign-out.
  useEffect(
    () => onSessionChange(() => queryClient.resetQueries({ queryKey: [USER_QUERY_KEY] })),
    [queryClient],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <Stack screenOptions={{ headerBackButtonDisplayMode: 'minimal' }}>
          <Stack.Screen name="index" options={{ title: 'What next?', headerLargeTitle: true }} />
          <Stack.Screen name="film/[tmdbId]" options={{ title: '' }} />
          <Stack.Screen name="about" options={{ title: 'About', presentation: 'modal' }} />
          <Stack.Screen name="account" options={{ title: 'Account' }} />
          <Stack.Screen name="review" options={{ title: 'Review queue' }} />
          <Stack.Screen name="my-edits" options={{ title: 'My edits' }} />
          <Stack.Screen name="propose" options={{ presentation: 'modal' }} />
        </Stack>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
