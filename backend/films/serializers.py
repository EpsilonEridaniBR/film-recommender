from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .importer import normalise_title
from .models import Credit, Film

TOP_CAST_IN_SUMMARY = 3


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
    top_cast = serializers.SerializerMethodField()

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
            "top_cast",
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

    def get_top_cast(self, film) -> list[str]:
        """The first few billed actors' names."""
        cast = [c for c in film.credits.all() if c.role == Credit.Role.CAST]
        return [c.person.name for c in cast[:TOP_CAST_IN_SUMMARY]]


class FilmSearchResultSerializer(FilmSummarySerializer):
    matched_title = serializers.SerializerMethodField()

    class Meta(FilmSummarySerializer.Meta):
        fields = FilmSummarySerializer.Meta.fields + ["matched_title"]

    def get_matched_title(self, film) -> str | None:
        """The title the search matched, when it isn't the one being shown
        (e.g. the original title of a foreign film); otherwise null."""
        matched = getattr(film, "matched_title", None)
        if not matched:
            return None
        shown = self.get_title(film)
        return None if normalise_title(matched) == normalise_title(shown) else matched


class FilmInfoSerializer(FilmSummarySerializer):
    """Full film info; the API adds suggestions (see suggestions.serializers)."""

    overview = serializers.SerializerMethodField()
    tagline = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    directors = serializers.SerializerMethodField()
    cast = serializers.SerializerMethodField()
    backdrop_url = serializers.SerializerMethodField()

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
        ]

    def get_overview(self, film) -> str:
        return film.safe_translation_getter("overview", any_language=True) or ""

    def get_tagline(self, film) -> str:
        return film.safe_translation_getter("tagline", any_language=True) or ""

    def get_genres(self, film) -> list[str]:
        return [str(g) for g in film.genres.all()]

    @extend_schema_field(PersonCreditSerializer(many=True))
    def get_directors(self, film):
        credits = [c for c in film.credits.all() if c.role == Credit.Role.DIRECTOR]
        return PersonCreditSerializer(credits, many=True).data

    @extend_schema_field(CastCreditSerializer(many=True))
    def get_cast(self, film):
        credits = [c for c in film.credits.all() if c.role == Credit.Role.CAST][:5]
        return CastCreditSerializer(credits, many=True).data

    def get_backdrop_url(self, film) -> str | None:
        return film.backdrop_url()
