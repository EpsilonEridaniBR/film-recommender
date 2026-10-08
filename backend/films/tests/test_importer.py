import io

import pytest

from films import importer
from films.models import Credit, Film, FilmSearchTitle, SkippedTmdbFilm
from films.tests.factories import parsed

pytestmark = pytest.mark.django_db


def test_upsert_is_idempotent_and_replaces_child_rows():
    importer.upsert_movies([parsed(1, "First Title", directors=["A", "B"])])
    importer.upsert_movies([parsed(1, "Other Title", directors=["C"])])

    film = Film.objects.get(tmdb_id=1)
    assert film.safe_translation_getter("title") == "Other Title"
    assert [c.person.name for c in film.credits.filter(role=Credit.Role.DIRECTOR)] == [
        "C"
    ]
    assert set(FilmSearchTitle.objects.values_list("language", "title", "text")) == {
        ("original", "Other Title", "other title"),
        ("en", "Other Title", "other title"),
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


def test_alternative_titles_are_searchable_but_not_duplicated():
    importer.upsert_movies(
        [
            parsed(
                807,
                "Se7en",
                alternative_titles=[("US", "Seven"), ("US", "Se7en"), ("GB", "Seven")],
            )
        ]
    )
    assert set(FilmSearchTitle.objects.values_list("language", "title")) == {
        ("original", "Se7en"),
        ("en", "Se7en"),
        ("alt-en", "Seven"),
    }


def test_alternative_duplicating_a_title_in_another_language_is_kept():
    # Se7en is "Seven" in French, but English searches don't look at French
    # titles, so the English alternative "Seven" must still be stored.
    importer.upsert_movies(
        [
            parsed(
                807,
                "Se7en",
                translations=[("fr", "FR", "Seven")],
                alternative_titles=[("US", "Seven")],
            )
        ]
    )
    assert ("alt-en", "Seven") in set(
        FilmSearchTitle.objects.values_list("language", "title")
    )


def test_films_passing_the_threshold_are_no_longer_skipped():
    importer.record_skipped([parsed(1, "New Release", vote_count=9)])
    client = FakeClient([parsed(1, "New Release", vote_count=178)])

    importer.fetch_and_store(client, [1], min_votes=25)

    assert Film.objects.filter(tmdb_id=1).exists()
    assert not SkippedTmdbFilm.objects.exists()


def test_skipped_to_recheck_ignores_how_recently_films_were_checked():
    importer.record_skipped([parsed(1, "Just Checked", vote_count=9)])
    importer.upsert_movies([parsed(2, "In Catalogue")])

    assert importer.skipped_to_recheck({1, 2, 3}) == [1]


class FakeSyncClient(FakeClient):
    def __init__(self, movies, changed=()):
        super().__init__(movies)
        self.changed = set(changed)

    def changed_movie_ids(self, start, end):
        return self.changed

    def close(self):
        pass


@pytest.fixture
def fake_tmdb(monkeypatch):
    """Point sync_tmdb at fake TMDB data: `setup(movies, changed, popular)`."""
    from films import tmdb

    def setup(movies, changed=(), popular=()):
        client = FakeSyncClient(movies, changed)
        monkeypatch.setattr(tmdb, "TmdbClient", lambda: client)
        monkeypatch.setattr(tmdb, "download_export", lambda: b"")
        monkeypatch.setattr(
            tmdb, "most_popular_ids", lambda export, limit: list(popular)[:limit]
        )
        monkeypatch.setattr(importer, "sync_genres", lambda client: None)

    return setup


def test_sync_rechecks_recently_skipped_films_that_are_changed_or_popular(fake_tmdb):
    from django.core.management import call_command

    importer.record_skipped(
        [
            parsed(1, "Changed Release", vote_count=9),
            parsed(2, "Popular Release", vote_count=9),
            parsed(3, "Still Obscure", vote_count=9),
        ]
    )
    fake_tmdb(
        [
            parsed(1, "Changed Release", vote_count=178),
            parsed(2, "Popular Release", vote_count=178),
            parsed(3, "Still Obscure", vote_count=178),
        ],
        changed={1},
        popular=[2, 3],
    )

    call_command("sync_tmdb", "--recheck-popular", "1", stdout=io.StringIO())

    # 3 is a candidate but not in the top 1 and unchanged: it waits the usual 30 days.
    assert set(Film.objects.values_list("tmdb_id", flat=True)) == {1, 2}


def test_sync_ids_fetches_only_those_films(fake_tmdb):
    from django.core.management import call_command

    fake_tmdb(
        [parsed(1, "Wanted", vote_count=178), parsed(2, "Not Asked For")],
        changed={2},
        popular=[2],
    )

    call_command("sync_tmdb", "--ids", "1", stdout=io.StringIO())

    assert list(Film.objects.values_list("tmdb_id", flat=True)) == [1]
