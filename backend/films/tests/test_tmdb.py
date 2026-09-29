from films.importer import normalise_title
from films.tests.factories import parsed


def test_picks_preferred_region_for_each_language():
    movie = parsed(
        329865,
        "Arrival",
        translations=[
            ("fr", "CA", "L'Arrivée"),
            ("fr", "FR", "Premier Contact"),
            ("pt", "BR", "A Chegada"),
            ("ja", "JP", "メッセージ"),
        ],
    )
    assert movie.translations["en"]["title"] == "Arrival"
    assert movie.translations["fr"]["title"] == "Premier Contact"
    assert movie.translations["pt"]["title"] == "A Chegada"
    assert "ja" not in movie.translations


def test_empty_translated_title_falls_back_to_original_in_own_language():
    movie = parsed(
        194,
        "Amélie",
        original_title="Le Fabuleux Destin d'Amélie Poulain",
        original_language="fr",
        translations=[("fr", "FR", ""), ("de", "DE", "")],
    )
    assert movie.translations["fr"]["title"] == "Le Fabuleux Destin d'Amélie Poulain"
    assert movie.translations["de"]["title"] == "Amélie"


def test_original_language_row_added_when_tmdb_has_none():
    movie = parsed(
        11216,
        "Cinema Paradiso",
        original_title="Nuovo Cinema Paradiso",
        original_language="it",
    )
    assert movie.translations["it"]["title"] == "Nuovo Cinema Paradiso"


def test_credits_are_parsed():
    movie = parsed(1, "Film", directors=["A", "B"])
    assert [d["name"] for d in movie.directors] == ["A", "B"]
    assert movie.cast[0]["character"] == "Hero"


def test_normalise_title():
    assert normalise_title("Amélie!") == "amelie"
    assert normalise_title("Spider-Man: No Way Home") == "spider man no way home"
    assert normalise_title("  Alien³ ") == "alien3"
