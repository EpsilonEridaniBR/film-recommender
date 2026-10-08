import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, appLanguage, unwrap } from './client';
import type { components } from './schema';

export type FilmSummary = components['schemas']['FilmSummary'];
export type FilmSearchResult = components['schemas']['FilmSearchResult'];
export type FilmDetail = components['schemas']['FilmDetail'];
export type Suggestion = components['schemas']['Suggestion'];

export const MIN_SEARCH_LENGTH = 2;

export function useFilmSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: ['films', 'search', appLanguage(), q],
    queryFn: async ({ signal }) =>
      unwrap(await api.GET('/api/v1/films/search/', { params: { query: { q } }, signal })),
    enabled: q.length >= MIN_SEARCH_LENGTH,
    // Keep showing the last results while the next ones load, so the list doesn't flash.
    placeholderData: keepPreviousData,
  });
}

export function useFilm(tmdbId: number) {
  return useQuery({
    queryKey: ['films', 'detail', appLanguage(), tmdbId],
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET('/api/v1/films/{tmdb_id}/', {
          params: { path: { tmdb_id: tmdbId } },
          signal,
        }),
      ),
  });
}
