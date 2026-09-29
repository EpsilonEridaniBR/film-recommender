"""Loads TMDB data into the catalogue. Shared by import_tmdb and sync_tmdb."""

import datetime as dt
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Credit, Film, FilmSearchTitle, Genre, Person, SkippedTmdbFilm

logger = logging.getLogger(__name__)

FilmTranslation = Film._parler_meta.root_model
GenreTranslation = Genre._parler_meta.root_model
FilmGenre = Film.genres.through

FILM_FIELDS = [
    "imdb_id",
    "original_title",
    "original_language",
    "release_date",
    "runtime",
    "poster_path",
    "backdrop_path",
    "popularity",
    "vote_count",
    "vote_average",
    "synced_at",
]


def normalise_title(text):
    """Lower-case, strip accents and punctuation: 'Amélie!' -> 'amelie'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w]+", " ", text.lower())
    return " ".join(text.split())


def sync_genres(client):
    languages = [code for code, _ in settings.LANGUAGES]
    names = {}  # tmdb_id -> {language: name}
    for language in languages:
        for genre in client.genres(language):
            names.setdefault(genre["id"], {})[language] = genre["name"]

    with transaction.atomic():
        for tmdb_id, by_language in names.items():
            genre, _ = Genre.objects.get_or_create(tmdb_id=tmdb_id)
            for language, name in by_language.items():
                if name:
                    genre.set_current_language(language)
                    genre.name = name
            genre.save()
    return len(names)


@transaction.atomic
def upsert_movies(movies):
    """Insert or update a batch of ParsedMovie objects in a few bulk queries."""
    if not movies:
        return
    now = timezone.now()

    films = Film.objects.bulk_create(
        [
            Film(
                tmdb_id=m.tmdb_id,
                imdb_id=m.imdb_id,
                original_title=m.original_title[:500],
                original_language=m.original_language,
                release_date=m.release_date,
                runtime=m.runtime,
                poster_path=m.poster_path,
                backdrop_path=m.backdrop_path,
                popularity=m.popularity,
                vote_count=m.vote_count,
                vote_average=m.vote_average,
                synced_at=now,
            )
            for m in movies
        ],
        update_conflicts=True,
        unique_fields=["tmdb_id"],
        update_fields=FILM_FIELDS,
    )
    film_ids = {f.tmdb_id: f.pk for f in films}
    pks = list(film_ids.values())

    # Replace the per-film child rows wholesale; simpler than diffing.
    FilmTranslation.objects.filter(master_id__in=pks).delete()
    FilmGenre.objects.filter(film_id__in=pks).delete()
    Credit.objects.filter(film_id__in=pks).delete()
    FilmSearchTitle.objects.filter(film_id__in=pks).delete()

    FilmTranslation.objects.bulk_create(
        FilmTranslation(
            master_id=film_ids[m.tmdb_id],
            language_code=language,
            title=t["title"][:500],
            overview=t["overview"],
            tagline=t["tagline"][:500],
        )
        for m in movies
        for language, t in m.translations.items()
    )

    genre_ids = dict(Genre.objects.values_list("tmdb_id", "pk"))
    FilmGenre.objects.bulk_create(
        FilmGenre(film_id=film_ids[m.tmdb_id], genre_id=genre_ids[g])
        for m in movies
        for g in set(m.genre_ids)
        if g in genre_ids
    )

    people = {}
    for m in movies:
        for p in m.directors + m.cast:
            people[p["tmdb_id"]] = p
    Person.objects.bulk_create(
        [
            Person(
                tmdb_id=p["tmdb_id"],
                name=p["name"][:255],
                profile_path=p["profile_path"] or "",
            )
            for p in people.values()
        ],
        update_conflicts=True,
        unique_fields=["tmdb_id"],
        update_fields=["name", "profile_path"],
    )
    person_ids = dict(
        Person.objects.filter(tmdb_id__in=people).values_list("tmdb_id", "pk")
    )

    credits = {}
    for m in movies:
        film_id = film_ids[m.tmdb_id]
        for order, d in enumerate(m.directors):
            key = (film_id, person_ids[d["tmdb_id"]], Credit.Role.DIRECTOR)
            credits.setdefault(key, Credit(order=order))
        for c in m.cast:
            key = (film_id, person_ids[c["tmdb_id"]], Credit.Role.CAST)
            credits.setdefault(
                key, Credit(order=c["order"], character=c["character"][:500])
            )
    for (film_id, person_id, role), credit in credits.items():
        credit.film_id, credit.person_id, credit.role = film_id, person_id, role
    Credit.objects.bulk_create(credits.values())

    FilmSearchTitle.objects.bulk_create(
        FilmSearchTitle(film_id=film_ids[m.tmdb_id], text=text[:500])
        for m in movies
        for text in {
            normalise_title(title)
            for title in [m.original_title]
            + [t["title"] for t in m.translations.values()]
        }
        if text
    )

    SkippedTmdbFilm.objects.filter(tmdb_id__in=film_ids).delete()


def record_skipped(movies):
    now = timezone.now()
    SkippedTmdbFilm.objects.bulk_create(
        [
            SkippedTmdbFilm(tmdb_id=m.tmdb_id, vote_count=m.vote_count, checked_at=now)
            for m in movies
        ],
        update_conflicts=True,
        unique_fields=["tmdb_id"],
        update_fields=["vote_count", "checked_at"],
    )


def fetch_and_store(client, tmdb_ids, min_votes, batch_size=500, workers=16, log=None):
    """Fetch films from TMDB concurrently and store those meeting `min_votes`.
    Films already in the catalogue are always kept up to date, even if they
    now fall below the threshold, because suggestions may point at them."""
    log = log or logger.info
    tmdb_ids = list(tmdb_ids)
    existing = set(
        Film.objects.filter(tmdb_id__in=tmdb_ids).values_list("tmdb_id", flat=True)
    )
    stored = skipped = missing = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(tmdb_ids), batch_size):
            batch = tmdb_ids[start : start + batch_size]
            results = list(pool.map(client.movie, batch))
            missing += sum(r is None for r in results)
            movies = [r for r in results if r and not r.adult]
            keep, below = [], []
            for m in movies:
                meets = m.vote_count >= min_votes or m.tmdb_id in existing
                (keep if meets else below).append(m)
            upsert_movies(keep)
            record_skipped(below)
            stored += len(keep)
            skipped += len(below)
            log(
                f"{min(start + batch_size, len(tmdb_ids))}/{len(tmdb_ids)} fetched "
                f"- {stored} stored, {skipped} below threshold, {missing} not found"
            )
    return stored, skipped, missing


def ids_needing_fetch(candidate_ids, refresh=False, recheck_skipped_after_days=30):
    """Drop candidates we already have, and ones recently found below threshold."""
    candidate_ids = list(candidate_ids)
    if refresh:
        return candidate_ids
    have = set(Film.objects.values_list("tmdb_id", flat=True))
    cutoff = timezone.now() - dt.timedelta(days=recheck_skipped_after_days)
    recently_skipped = set(
        SkippedTmdbFilm.objects.filter(checked_at__gte=cutoff).values_list(
            "tmdb_id", flat=True
        )
    )
    return [i for i in candidate_ids if i not in have and i not in recently_skipped]
