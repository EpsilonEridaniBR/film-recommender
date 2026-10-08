"""Thin TMDB API client used by the import and sync commands.

The app never calls TMDB at runtime; only management commands use this.
"""

import datetime as dt
import gzip
import heapq
import io
import json
import logging
import threading
import time
from dataclasses import dataclass, field

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.themoviedb.org/3"
EXPORT_URL = "https://files.tmdb.org/p/exports/movie_ids_{date}.json.gz"

# TMDB region variants to use for each catalogue language, in order of preference.
LOCALE_PREFERENCES = {
    "en": ["US", "GB"],
    "fr": ["FR", "CA"],
    "de": ["DE", "AT", "CH"],
    "es": ["ES", "MX"],
    "it": ["IT"],
    "pt": ["BR", "PT"],
}

CAST_LIMIT = 10

# Alternative titles are kept from these regions only, as the language people
# there would search in. (Canada is left out: English or French is unclear.)
ALTERNATIVE_TITLE_REGIONS = {
    "US": "en", "GB": "en",
    "FR": "fr",
    "DE": "de", "AT": "de",
    "ES": "es", "MX": "es",
    "IT": "it",
    "BR": "pt", "PT": "pt",
}  # fmt: skip


class TmdbError(Exception):
    pass


class RateLimiter:
    """Simple thread-safe limiter: at most `rate` calls per second."""

    def __init__(self, rate):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next_time = time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            wait_for = self.next_time - now
            self.next_time = max(now, self.next_time) + self.interval
        if wait_for > 0:
            time.sleep(wait_for)


class TmdbClient:
    def __init__(self, token=None, rate=40, max_retries=5):
        token = token or settings.TMDB_API_KEY
        if not token:
            raise TmdbError("TMDB_API_KEY is not set.")
        self.http = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
        self.limiter = RateLimiter(rate)
        self.max_retries = max_retries

    def get(self, path, **params):
        """GET a TMDB endpoint. Returns None for 404 (e.g. deleted films)."""
        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                response = self.http.get(path, params=params)
            except httpx.TransportError as exc:
                logger.warning("TMDB %s failed (%s), retrying", path, exc)
                time.sleep(2**attempt)
                continue
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                delay = float(response.headers.get("Retry-After", 2**attempt))
                logger.warning(
                    "TMDB %s returned %s, retrying in %ss",
                    path,
                    response.status_code,
                    delay,
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        raise TmdbError(f"TMDB {path} failed after {self.max_retries} attempts")

    def movie(self, tmdb_id):
        data = self.get(
            f"/movie/{tmdb_id}",
            append_to_response="credits,translations,external_ids,alternative_titles",
        )
        return parse_movie(data) if data else None

    def search_movies(self, query, year=None):
        params = {"query": query, "include_adult": "false"}
        if year:
            params["year"] = year
        return self.get("/search/movie", **params)["results"]

    def genres(self, language):
        return self.get("/genre/movie/list", language=language)["genres"]

    def changed_movie_ids(self, start_date, end_date):
        ids, page, total_pages = set(), 1, 1
        while page <= total_pages:
            data = self.get(
                "/movie/changes",
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                page=page,
            )
            ids.update(item["id"] for item in data["results"] if not item.get("adult"))
            total_pages = data["total_pages"]
            page += 1
        return ids

    def close(self):
        self.http.close()


def download_export(max_days_back=3):
    """Download the most recent daily export of all TMDB movie IDs."""
    today = dt.datetime.now(dt.UTC).date()
    for days_back in range(max_days_back + 1):
        date = (today - dt.timedelta(days=days_back)).strftime("%m_%d_%Y")
        response = httpx.get(EXPORT_URL.format(date=date), timeout=120)
        if response.status_code == 200:
            logger.info("Using TMDB export for %s", date)
            return response.content
    raise TmdbError("No TMDB daily export found for the last few days.")


def most_popular_ids(export_gz, limit):
    """Stream the export and return the `limit` most popular non-adult film IDs,
    most popular first. Streams line by line to keep memory low."""

    def rows():
        with gzip.GzipFile(fileobj=io.BytesIO(export_gz)) as lines:
            for line in lines:
                row = json.loads(line)
                if not row.get("adult") and not row.get("video"):
                    yield row["popularity"], row["id"]

    return [tmdb_id for _, tmdb_id in heapq.nlargest(limit, rows())]


@dataclass
class ParsedMovie:
    tmdb_id: int
    imdb_id: str
    original_title: str
    original_language: str
    release_date: dt.date | None
    runtime: int | None
    poster_path: str
    backdrop_path: str
    popularity: float
    vote_count: int
    vote_average: float
    adult: bool
    genre_ids: list[int]
    # language code -> {"title", "overview", "tagline"}
    translations: dict[str, dict[str, str]]
    directors: list[dict] = field(default_factory=list)
    cast: list[dict] = field(default_factory=list)
    # language -> other titles the film is known by there, e.g. "Seven" for Se7en.
    alternative_titles: dict[str, list[str]] = field(default_factory=dict)


def parse_movie(data):
    english = {
        "title": data.get("title") or data.get("original_title") or "",
        "overview": data.get("overview") or "",
        "tagline": data.get("tagline") or "",
    }
    translations = {"en": english}
    original_title = data.get("original_title") or english["title"]
    original_language = data.get("original_language") or ""

    def untranslated_title(language):
        # TMDB leaves a translated title empty when it's unchanged: the original
        # title in the film's own language, otherwise the English one.
        return original_title if language == original_language else english["title"]

    by_locale = {
        (t["iso_639_1"], t["iso_3166_1"]): t["data"]
        for t in data.get("translations", {}).get("translations", [])
    }
    for language, regions in LOCALE_PREFERENCES.items():
        if language == "en":
            continue
        for region in regions:
            t = by_locale.get((language, region))
            if t and (t.get("title") or t.get("overview")):
                translations[language] = {
                    "title": t.get("title") or untranslated_title(language),
                    "overview": t.get("overview") or "",
                    "tagline": t.get("tagline") or "",
                }
                break

    # Films are always searchable and shown by their original title in their own
    # language, even if TMDB has no translation entry for it.
    if (
        original_language in LOCALE_PREFERENCES
        and original_language not in translations
    ):
        translations[original_language] = {**english, "title": original_title}

    credits = data.get("credits", {})
    directors = [
        {"tmdb_id": c["id"], "name": c["name"], "profile_path": c.get("profile_path")}
        for c in credits.get("crew", [])
        if c.get("job") == "Director"
    ]
    cast = [
        {
            "tmdb_id": c["id"],
            "name": c["name"],
            "profile_path": c.get("profile_path"),
            "character": c.get("character") or "",
            "order": c.get("order", i),
        }
        for i, c in enumerate(credits.get("cast", [])[:CAST_LIMIT])
    ]

    alternative_titles = {}
    for alt in data.get("alternative_titles", {}).get("titles", []):
        language = ALTERNATIVE_TITLE_REGIONS.get(alt.get("iso_3166_1"))
        title = (alt.get("title") or "").strip()
        if language and title:
            alternative_titles.setdefault(language, []).append(title)

    release_date = None
    if data.get("release_date"):
        try:
            release_date = dt.date.fromisoformat(data["release_date"])
        except ValueError:
            pass

    return ParsedMovie(
        tmdb_id=data["id"],
        imdb_id=data.get("imdb_id")
        or data.get("external_ids", {}).get("imdb_id")
        or "",
        original_title=original_title,
        original_language=original_language,
        release_date=release_date,
        runtime=data.get("runtime") or None,
        poster_path=data.get("poster_path") or "",
        backdrop_path=data.get("backdrop_path") or "",
        popularity=data.get("popularity") or 0,
        vote_count=data.get("vote_count") or 0,
        vote_average=data.get("vote_average") or 0,
        adult=bool(data.get("adult")),
        genre_ids=[g["id"] for g in data.get("genres", [])],
        translations=translations,
        directors=directors,
        cast=cast,
        alternative_titles=alternative_titles,
    )
