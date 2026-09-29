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
