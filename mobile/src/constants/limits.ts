// These mirror the backend's settings, which enforce them; the app uses them
// to stop people going over before they submit.

/** EXPLANATION_MAX_CHARS in backend/suggestions/services.py. */
export const EXPLANATION_MAX_CHARS = 500;

/** AUDIO_MAX_SECONDS in backend/core/settings.py. */
export const AUDIO_MAX_SECONDS = 60;

/** APPROVALS_REQUIRED and REJECTIONS_REQUIRED in backend/core/settings.py. */
export const VOTES_REQUIRED = 2;
