import zlib

from films.tmdb import parse_movie


def tmdb_movie(
    tmdb_id,
    title,
    *,
    original_title=None,
    original_language="en",
    vote_count=100,
    translations=(),
    directors=("Some Director",),
    genres=(),
    release_date="2016-11-10",
    alternative_titles=(),
):
    """Build a raw TMDB /movie response (with appended credits/translations)."""
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": original_title or title,
        "original_language": original_language,
        "overview": f"{title} overview",
        "tagline": "",
        "release_date": release_date,
        "runtime": 100,
        "poster_path": f"/{tmdb_id}.jpg",
        "backdrop_path": "",
        "popularity": 10.0,
        "vote_count": vote_count,
        "vote_average": 7.5,
        "adult": False,
        "imdb_id": f"tt{tmdb_id}",
        "genres": [{"id": g, "name": str(g)} for g in genres],
        "credits": {
            "crew": [
                {
                    "id": zlib.crc32(name.encode()) % 1_000_000,
                    "name": name,
                    "job": "Director",
                }
                for name in directors
            ],
            "cast": [{"id": 2000, "name": "Lead Actor", "character": "Hero"}],
        },
        "alternative_titles": {
            "titles": [
                {"iso_3166_1": region, "title": t, "type": ""}
                for region, t in alternative_titles
            ]
        },
        "translations": {
            "translations": [
                {
                    "iso_639_1": lang,
                    "iso_3166_1": region,
                    "data": {"title": t, "overview": f"{lang} overview", "tagline": ""},
                }
                for lang, region, t in translations
            ]
        },
    }


def parsed(*args, **kwargs):
    return parse_movie(tmdb_movie(*args, **kwargs))
