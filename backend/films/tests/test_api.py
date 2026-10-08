import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from films import importer
from films.tests.factories import parsed

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogue():
    importer.upsert_movies(
        [
            parsed(
                329865,
                "Arrival",
                vote_count=20000,
                translations=[("fr", "FR", "Premier Contact")],
                directors=["Denis Villeneuve"],
            ),
            parsed(10824, "The Arrival", vote_count=500, release_date="1996-05-31"),
            parsed(14160, "Up", vote_count=20000),
            # Only its Portuguese title mentions Blade Runner.
            parsed(
                473072,
                "2036: Nexus Dawn",
                vote_count=400,
                translations=[("pt", "BR", "Blade Runner 2036: Nexus Dawn")],
            ),
            parsed(78, "Blade Runner", vote_count=15000),
            parsed(389, "12 Angry Men", vote_count=9000),
            parsed(1367, "Rocky II", vote_count=4000),
            parsed(
                807,
                "Se7en",
                vote_count=21000,
                alternative_titles=[("US", "Seven"), ("IT", "Seven Italiano")],
            ),
            parsed(346, "Seven Samurai", vote_count=4000),
            parsed(19995, "Upgrade", vote_count=5000),
            parsed(
                194,
                "Amélie",
                original_title="Le Fabuleux Destin d'Amélie Poulain",
                original_language="fr",
            ),
        ]
    )


def titles(response):
    return [f["title"] for f in response.json()]


def test_search_ranks_exact_and_popular_matches_first(client, catalogue):
    response = client.get("/api/v1/films/search/", {"q": "arrival"})
    assert response.status_code == 200
    assert titles(response)[:2] == ["Arrival", "The Arrival"]


def test_search_is_accent_insensitive_and_finds_original_titles(client, catalogue):
    assert titles(client.get("/api/v1/films/search/", {"q": "amelie"})) == ["Amélie"]
    assert titles(client.get("/api/v1/films/search/", {"q": "fabuleux destin"})) == [
        "Amélie"
    ]


def test_search_ignores_titles_in_other_languages(client, catalogue):
    english = client.get("/api/v1/films/search/", {"q": "blade runner"})
    assert titles(english) == ["Blade Runner"]

    portuguese = client.get(
        "/api/v1/films/search/", {"q": "blade runner"}, HTTP_ACCEPT_LANGUAGE="pt"
    )
    assert titles(portuguese) == ["Blade Runner", "Blade Runner 2036: Nexus Dawn"]


def test_search_reports_which_title_matched(client, catalogue):
    [amelie] = client.get("/api/v1/films/search/", {"q": "fabuleux destin"}).json()
    assert amelie["matched_title"] == "Le Fabuleux Destin d'Amélie Poulain"

    [arrival, *_] = client.get(
        "/api/v1/films/search/", {"q": "arrival"}, HTTP_ACCEPT_LANGUAGE="fr"
    ).json()
    assert (arrival["title"], arrival["matched_title"]) == (
        "Premier Contact",
        "Arrival",
    )


def test_matched_title_is_null_when_it_is_the_title_shown(client, catalogue):
    [amelie] = client.get("/api/v1/films/search/", {"q": "amelie"}).json()
    assert amelie["matched_title"] is None


def test_search_matches_short_prefixes(client, catalogue):
    assert titles(client.get("/api/v1/films/search/", {"q": "up"}))[:2] == [
        "Up",
        "Upgrade",
    ]


def test_search_tolerates_typos(client, catalogue):
    assert "Arrival" in titles(client.get("/api/v1/films/search/", {"q": "arival"}))


def test_search_returns_titles_in_requested_language(client, catalogue):
    response = client.get(
        "/api/v1/films/search/", {"q": "premier contact"}, HTTP_ACCEPT_LANGUAGE="fr"
    )
    assert titles(response) == ["Premier Contact"]


def test_search_results_include_top_cast(client, catalogue):
    result = client.get("/api/v1/films/search/", {"q": "arrival"}).json()[0]
    assert result["top_cast"] == ["Lead Actor"]


def test_search_requires_two_characters(client, catalogue):
    assert client.get("/api/v1/films/search/", {"q": "u"}).json() == []


def test_search_query_count_is_constant(client, catalogue):
    with CaptureQueriesContext(connection) as queries:
        client.get("/api/v1/films/search/", {"q": "a"})
        client.get("/api/v1/films/search/", {"q": "arrival"})
    assert len(queries) <= 6


def test_film_detail(client, catalogue):
    response = client.get("/api/v1/films/329865/", HTTP_ACCEPT_LANGUAGE="fr")
    assert response.status_code == 200
    film = response.json()
    assert film["title"] == "Premier Contact"
    assert film["original_title"] == "Arrival"
    assert film["year"] == 2016
    assert film["directors"][0]["name"] == "Denis Villeneuve"
    assert film["poster_url"].endswith("/w500/329865.jpg")


def test_film_detail_falls_back_to_english(client, catalogue):
    response = client.get("/api/v1/films/329865/", HTTP_ACCEPT_LANGUAGE="de")
    assert response.json()["title"] == "Arrival"


def test_film_detail_404(client):
    assert client.get("/api/v1/films/1/").status_code == 404


@pytest.mark.parametrize("query", ["twelve angry men", "12 angry men", "twelve angry"])
def test_search_treats_number_words_and_digits_alike(client, catalogue, query):
    assert (
        titles(client.get("/api/v1/films/search/", {"q": query}))[0] == "12 Angry Men"
    )


@pytest.mark.parametrize("query", ["rocky 2", "rocky ii", "rocky two"])
def test_search_matches_roman_numerals(client, catalogue, query):
    assert titles(client.get("/api/v1/films/search/", {"q": query}))[0] == "Rocky II"


def test_search_finds_films_by_alternative_title(client, catalogue):
    results = client.get("/api/v1/films/search/", {"q": "seven"}).json()
    se7en = next(f for f in results if f["title"] == "Se7en")
    assert se7en["matched_title"] == "Seven"


def test_alternative_titles_rank_below_real_titles(client):
    importer.upsert_movies(
        [
            parsed(1, "Se7en", vote_count=1000, alternative_titles=[("US", "Seven")]),
            parsed(2, "Seven", vote_count=1000),
        ]
    )
    assert titles(client.get("/api/v1/films/search/", {"q": "seven"})) == [
        "Seven",
        "Se7en",
    ]


def test_alternative_titles_in_other_languages_are_ignored(client, catalogue):
    assert "Se7en" not in titles(
        client.get("/api/v1/films/search/", {"q": "seven italiano"})
    )


def test_search_ordering_for_seven(client):
    """Exact beats starts-with beats contains, with popularity able to lift a
    well-known film (Se7en, via its alternative title) to the top."""
    importer.upsert_movies(
        [
            parsed(
                807, "Se7en", vote_count=24000, alternative_titles=[("US", "Seven")]
            ),
            parsed(1, "Seven", vote_count=47, release_date="1979-01-01"),
            parsed(2, "Seven Pounds", vote_count=7400),
            parsed(3, "Seven Samurai", vote_count=4400),
            parsed(4, "Furious 7", vote_count=11500),
        ]
    )
    assert titles(client.get("/api/v1/films/search/", {"q": "seven"})) == [
        "Se7en",
        "Seven",
        "Seven Pounds",
        "Seven Samurai",
        "Furious 7",
    ]


def test_starts_with_beats_contains(client, catalogue):
    # "Up" (exact), "Upgrade" (starts with); a film merely containing "up" is later.
    importer.upsert_movies([parsed(5, "Don't Look Up", vote_count=5000)])
    results = titles(client.get("/api/v1/films/search/", {"q": "up"}))
    assert results.index("Upgrade") < results.index("Don't Look Up")
