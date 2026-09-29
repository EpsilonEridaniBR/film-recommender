from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Case, F, Max, Q, Value, When
from django.db.models.functions import Greatest, Log

from .importer import normalise_title
from .models import Film


def search_films(query, limit=20):
    """Fuzzy title search across every language's title, favouring films
    with more votes. Returns a queryset of Films, best match first."""
    q = normalise_title(query)
    if not q:
        return Film.objects.none()

    # Exact and prefix matches beat fuzzy ones, so short queries like "up" work.
    match = Greatest(
        TrigramWordSimilarity(q, "search_titles__text"),
        Case(
            When(search_titles__text=q, then=Value(1.5)),
            When(search_titles__text__startswith=q, then=Value(1.0)),
            default=Value(0.0),
        ),
    )
    return (
        Film.objects.filter(
            Q(search_titles__text__trigram_word_similar=q)
            | Q(search_titles__text__startswith=q)
        )
        .annotate(match=Max(match))
        .annotate(score=F("match") + 0.1 * Log(10, F("vote_count") + 1))
        .order_by("-score", "-vote_count")[:limit]
    )
