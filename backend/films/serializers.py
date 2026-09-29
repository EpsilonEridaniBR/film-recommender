from rest_framework import serializers

from .importer import normalise_title
from .models import Credit, Film


class PersonCreditSerializer(serializers.Serializer):
    tmdb_id = serializers.IntegerField(source="person.tmdb_id")
    name = serializers.CharField(source="person.name")


class CastCreditSerializer(PersonCreditSerializer):
    character = serializers.CharField()


class FilmSummarySerializer(serializers.ModelSerializer):
    """Compact film info for search results and suggestion cards."""

    title = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    directors = serializers.SerializerMethodField()

    class Meta:
        model = Film
        fields = [
            "tmdb_id",
            "title",
            "original_title",
            "year",
            "runtime",
            "poster_url",
            "directors",
        ]

    def get_title(self, film) -> str:
        return (
            film.safe_translation_getter("title", any_language=True)
            or film.original_title
        )

    def get_year(self, film) -> int | None:
        return film.release_date.year if film.release_date else None

    def get_poster_url(self, film) -> str | None:
        return film.poster_url()

    def get_directors(self, film) -> list[str]:
        return [
            c.person.name for c in film.credits.all() if c.role == Credit.Role.DIRECTOR
        ]


class FilmDetailSerializer(FilmSummarySerializer):
    overview = serializers.SerializerMethodField()
    tagline = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    directors = serializers.SerializerMethodField()
    cast = serializers.SerializerMethodField()
    backdrop_url = serializers.SerializerMethodField()
    suggestions = serializers.SerializerMethodField()

    class Meta(FilmSummarySerializer.Meta):
        fields = FilmSummarySerializer.Meta.fields + [
            "imdb_id",
            "original_language",
            "release_date",
            "overview",
            "tagline",
            "genres",
            "cast",
            "vote_average",
            "vote_count",
            "backdrop_url",
            "suggestions",
        ]

    def get_overview(self, film) -> str:
        return film.safe_translation_getter("overview", any_language=True) or ""

    def get_tagline(self, film) -> str:
        return film.safe_translation_getter("tagline", any_language=True) or ""

    def get_genres(self, film) -> list[str]:
        return [str(g) for g in film.genres.all()]

    def get_directors(self, film) -> list[dict]:
        credits = [c for c in film.credits.all() if c.role == Credit.Role.DIRECTOR]
        return PersonCreditSerializer(credits, many=True).data

    def get_cast(self, film) -> list[dict]:
        credits = [c for c in film.credits.all() if c.role == Credit.Role.CAST][:5]
        return CastCreditSerializer(credits, many=True).data

    def get_backdrop_url(self, film) -> str | None:
        return film.backdrop_url()

    def get_suggestions(self, film) -> list[dict]:
        # Imported here: suggestions' serializers build on this module.
        from suggestions.serializers import SuggestionSerializer

        data = SuggestionSerializer(
            film.suggestions.all(), many=True, context=self.context
        ).data
        # Suggestions have no order of their own: alphabetical in the reader's language.
        return sorted(data, key=lambda s: normalise_title(s["film"]["title"]))
