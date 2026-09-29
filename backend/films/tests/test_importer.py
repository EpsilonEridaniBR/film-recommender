import pytest

from films import importer
from films.models import Credit, Film, FilmSearchTitle, SkippedTmdbFilm
from films.tests.factories import parsed

pytestmark = pytest.mark.django_db


def test_upsert_is_idempotent_and_replaces_child_rows():
    importer.upsert_movies([parsed(1, "First Title", directors=["A", "B"])])
    importer.upsert_movies([parsed(1, "Second Title", directors=["C"])])

    film = Film.objects.get(tmdb_id=1)
    assert film.safe_translation_getter("title") == "Second Title"
    assert [c.person.name for c in film.credits.filter(role=Credit.Role.DIRECTOR)] == [
        "C"
    ]
    assert set(FilmSearchTitle.objects.values_list("text", flat=True)) == {
        "second title"
    }


class FakeClient:
    def __init__(self, movies):
        self.movies = {m.tmdb_id: m for m in movies}

    def movie(self, tmdb_id):
        return self.movies.get(tmdb_id)


def test_fetch_and_store_applies_vote_threshold():
    client = FakeClient(
        [parsed(1, "Popular", vote_count=500), parsed(2, "Obscure", vote_count=3)]
    )

    stored, skipped, missing = importer.fetch_and_store(client, [1, 2, 3], min_votes=25)

    assert (stored, skipped, missing) == (1, 1, 1)
    assert list(Film.objects.values_list("tmdb_id", flat=True)) == [1]
    assert SkippedTmdbFilm.objects.get().tmdb_id == 2


def test_existing_films_are_kept_even_below_threshold():
    importer.upsert_movies([parsed(1, "Once Popular", vote_count=500)])
    client = FakeClient([parsed(1, "Once Popular", vote_count=3)])

    importer.fetch_and_store(client, [1], min_votes=25)

    assert Film.objects.get(tmdb_id=1).vote_count == 3


def test_ids_needing_fetch_skips_known_and_recently_skipped():
    importer.upsert_movies([parsed(1, "Have It")])
    importer.record_skipped([parsed(2, "Too Obscure", vote_count=1)])

    assert importer.ids_needing_fetch([1, 2, 3]) == [3]
    assert importer.ids_needing_fetch([1, 2, 3], refresh=True) == [1, 2, 3]
