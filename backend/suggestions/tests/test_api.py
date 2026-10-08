from django.db import connection
from django.test.utils import CaptureQueriesContext

from suggestions import seeding


def add(films, source, *titles):
    for title in titles:
        seeding.create_seed_suggestion(
            films[source].pk, films[title].pk, f"Why {title}"
        )


def suggestion_titles(response):
    return [s["film"]["title"] for s in response.json()["suggestions"]]


def test_film_detail_lists_suggestions_alphabetically(client, films):
    add(films, "Casablanca", "Zodiac", "Up", "Arrival")

    response = client.get("/api/v1/films/289/")

    assert suggestion_titles(response) == ["Arrival", "Up", "Zodiac"]
    first = response.json()["suggestions"][0]
    assert first["explanation"] == "Why Arrival"
    assert first["audio_url"] is None
    assert first["film"]["tmdb_id"] == 329865


def test_suggestions_are_sorted_in_the_readers_language(client, films):
    add(films, "Casablanca", "Zodiac", "Up", "Arrival")

    response = client.get("/api/v1/films/289/", HTTP_ACCEPT_LANGUAGE="fr")

    assert suggestion_titles(response) == ["Là-haut", "Premier Contact", "Zodiac"]


def test_film_without_suggestions(client, films):
    assert client.get("/api/v1/films/289/").json()["suggestions"] == []


def test_film_detail_says_how_many_suggestions_are_allowed(client, films, settings):
    settings.SUGGESTIONS_PER_FILM = 4
    assert client.get("/api/v1/films/289/").json()["max_suggestions"] == 4


def test_detail_query_count_does_not_grow_with_suggestions(client, films):
    add(films, "Casablanca", "Arrival")
    with CaptureQueriesContext(connection) as one:
        client.get("/api/v1/films/289/")

    add(films, "Casablanca", "Up", "Zodiac")
    with CaptureQueriesContext(connection) as three:
        client.get("/api/v1/films/289/")

    assert len(three) == len(one)
