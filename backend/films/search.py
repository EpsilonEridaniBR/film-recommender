from django.conf import settings
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import (
    Case,
    F,
    FloatField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Greatest, Log

from .importer import normalise_title
from .models import Film, FilmSearchTitle

# How a title matching the search scores. Higher tiers always beat lower ones
# unless popularity (below) makes up the difference.
EXACT_MATCH = 1.5  # "seven" -> "Seven"
STARTS_WITH = 1.0  # "seven" -> "Seven Samurai"
# Containing the words elsewhere ("Furious 7"), or a fuzzy/typo match, scores
# up to this (trigram word similarity, scaled).
CONTAINS_AT_MOST = 0.8

# A match on an alternative title (e.g. "Seven" for Se7en) counts for a bit
# less than one on a real title, so real titles win close calls.
ALTERNATIVE_TITLE_WEIGHT = 0.9

# Added per tenfold increase in TMDB votes: 100 votes +0.4, 10,000 votes +0.8.
# People search for films they've just watched, which are usually well known.
POPULARITY_WEIGHT = 0.2


def match_score(q, prefix=""):
    """How well a search title matches `q`. `prefix` is the path from the
    queried model to FilmSearchTitle, e.g. "search_titles__"."""
    text = f"{prefix}text"
    score = Greatest(
        TrigramWordSimilarity(q, text) * CONTAINS_AT_MOST,
        Case(
            When(**{text: q}, then=Value(EXACT_MATCH)),
            When(**{f"{text}__startswith": q}, then=Value(STARTS_WITH)),
            default=Value(0.0),
        ),
    )
    weight = Case(
        When(
            **{f"{prefix}language__startswith": FilmSearchTitle.ALTERNATIVE_PREFIX},
            then=Value(ALTERNATIVE_TITLE_WEIGHT),
        ),
        default=Value(1.0),
        output_field=FloatField(),
    )
    return score * weight


def search_languages(language):
    """Which titles a search looks at: the original title, and titles (real and
    alternative) in the reader's language and in English, the fallback when a
    translation is missing. Titles in other languages are ignored, so films
    don't match on e.g. a Portuguese title the reader never sees."""
    languages = {language, settings.PARLER_DEFAULT_LANGUAGE_CODE}
    return (
        {FilmSearchTitle.ORIGINAL}
        | languages
        | {FilmSearchTitle.alternative(code) for code in languages}
    )


def search_films(query, language, limit=20):
    """Fuzzy title search, favouring films with more votes. Returns Films,
    best match first, each annotated with `matched_title`: the title that
    matched best, as written (e.g. the original title)."""
    q = normalise_title(query)
    if not q:
        return Film.objects.none()
    languages = search_languages(language)

    best_title = (
        FilmSearchTitle.objects.filter(film=OuterRef("pk"), language__in=languages)
        .annotate(score=match_score(q))
        # On a tie, prefer the reader's own language.
        .annotate(
            own_language=Case(When(language=language, then=Value(1)), default=Value(0))
        )
        .order_by("-score", "-own_language")
        .values("title")[:1]
    )
    return (
        Film.objects.filter(
            Q(search_titles__text__trigram_word_similar=q)
            | Q(search_titles__text__startswith=q),
            search_titles__language__in=languages,
        )
        .annotate(match=Max(match_score(q, prefix="search_titles__")))
        .annotate(score=F("match") + POPULARITY_WEIGHT * Log(10, F("vote_count") + 1))
        .annotate(matched_title=Subquery(best_title))
        .order_by("-score", "-vote_count")[:limit]
    )
