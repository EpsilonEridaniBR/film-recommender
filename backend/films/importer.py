"""Loads TMDB data into the catalogue. Shared by import_tmdb and sync_tmdb."""

import datetime as dt
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .numbers import words_to_digits
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
    """The form titles are searched in: lower-cased, accents and punctuation
    stripped, English number words as digits.
    'Amélie!' -> 'amelie'; 'Twelve Angry Men' -> '12 angry men'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w]+", " ", text.lower())
    return " ".join(words_to_digits(text.split()))


def search_titles(film_id, original_title, translations, alternative_titles=None):
    """FilmSearchTitle rows for a film: its original title, its title in each
    catalogue language, and alternative titles (e.g. "Seven" for Se7en).
    `translations` maps language -> {"title": ...}; `alternative_titles` maps
    language -> [title, ...]."""
    titles = [(FilmSearchTitle.ORIGINAL, original_title)] + [
        (language, t["title"]) for language, t in translations.items()
    ]
    for language, alternatives in (alternative_titles or {}).items():
        titles += [(FilmSearchTitle.alternative(language), t) for t in alternatives]

    rows = {}
    main_texts = {}  # language -> normalised texts of real titles
    for language, title in titles:
        if not FilmSearchTitle.is_alternative_language(language):
            main_texts.setdefault(language, set()).add(normalise_title(title)[:500])

    for language, title in titles:
        text = normalise_title(title)[:500]
        if not text:
            continue
        if FilmSearchTitle.is_alternative_language(language):
            # Skip an alternative that reads the same as a real title searched
            # alongside it. Real titles in other languages don't count: e.g.
            # Se7en's French title is "Seven", but English searches don't see it.
            base = language.removeprefix(FilmSearchTitle.ALTERNATIVE_PREFIX)
            searched_with = {base, FilmSearchTitle.ORIGINAL, "en"}
            if any(text in main_texts.get(other, ()) for other in searched_with):
                continue
        rows.setdefault(
            (language, text),
            FilmSearchTitle(
                film_id=film_id, language=language, title=title[:500], text=text
            ),
        )
    return list(rows.values())


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
        title
        for m in movies
        for title in search_titles(
            film_ids[m.tmdb_id], m.original_title, m.translations, m.alternative_titles
        )
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
            # Films that have now passed the threshold aren't "skipped" any more.
            SkippedTmdbFilm.objects.filter(
                tmdb_id__in=[m.tmdb_id for m in keep]
            ).delete()
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


def skipped_to_recheck(tmdb_ids):
    """Films among `tmdb_ids` that were below the vote threshold when last
    checked, however recently. Used for films that are changing or popular on
    TMDB, which is how new releases look while their vote counts climb, so
    they don't wait the usual 30 days to be checked again."""
    return list(
        SkippedTmdbFilm.objects.filter(tmdb_id__in=list(tmdb_ids)).values_list(
            "tmdb_id", flat=True
        )
    )
