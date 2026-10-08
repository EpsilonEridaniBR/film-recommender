import pytest

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


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Twelve Angry Men", "12 angry men"),
        ("12 Angry Men", "12 angry men"),
        ("Ten Things I Hate About You", "10 things i hate about you"),
        ("Two Thousand and One", "2001"),
        ("One Hundred and One Dalmatians", "101 dalmatians"),
        ("Nineteen Eighty-Four", "1984"),
        ("Twenty One Pistols", "21 pistols"),
        ("Seven Seven", "7 7"),
        ("Stand and Deliver", "stand and deliver"),
        ("The Forty-Year-Old Virgin", "the 40 year old virgin"),
        # Roman numerals (but not the word "I")
        ("Rocky II", "rocky 2"),
        ("Star Wars: Episode V", "star wars episode 5"),
        ("10 Things I Hate About You", "10 things i hate about you"),
        ("Civil War", "civil war"),
        # Ordinals, as words or digits
        ("The Second Best Exotic Marigold Hotel", "the 2 best exotic marigold hotel"),
        ("2nd Best Exotic Marigold Hotel", "2 best exotic marigold hotel"),
        ("21st Century Women", "21 century women"),
        ("Twenty-First Century Women", "21 century women"),
        ("50 First Dates", "51 dates"),
        ("Fifty First Dates", "51 dates"),
    ],
)
def test_normalise_title_turns_number_words_into_digits(title, expected):
    assert normalise_title(title) == expected


def test_alternative_titles_are_kept_for_catalogue_regions():
    movie = parsed(
        807,
        "Se7en",
        alternative_titles=[
            ("US", "Seven"),
            ("GB", "Seven"),
            ("BR", "Seven: Os Sete Crimes Capitais"),
            ("CA", "Sept"),
            ("JP", "セブン"),
        ],
    )
    assert movie.alternative_titles == {
        "en": ["Seven", "Seven"],
        "pt": ["Seven: Os Sete Crimes Capitais"],
    }
