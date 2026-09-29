from django.contrib import admin
from django.utils.html import format_html
from parler.admin import TranslatableAdmin
from unfold.admin import ModelAdmin, TabularInline

from .models import Credit, Film, Genre, Person, SkippedTmdbFilm


class ReadOnlyAdminMixin:
    """Catalogue data comes from TMDB and is overwritten on every sync,
    so it's view-only in the admin."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CreditInline(ReadOnlyAdminMixin, TabularInline):
    model = Credit
    fields = ["role", "person", "character", "order"]
    readonly_fields = fields
    extra = 0


@admin.register(Film)
class FilmAdmin(ReadOnlyAdminMixin, TranslatableAdmin, ModelAdmin):
    list_display = ["poster", "__str__", "original_title", "vote_count", "tmdb_link"]
    list_display_links = ["__str__"]
    search_fields = ["search_titles__text", "original_title", "=tmdb_id", "=imdb_id"]
    list_filter = ["genres", "original_language"]
    ordering = ["-vote_count"]
    inlines = [CreditInline]
    readonly_fields = ["poster", "tmdb_link", "genre_list"]
    fieldsets = [
        (None, {"fields": ["poster", "title", "tagline", "overview"]}),
        (
            "Details",
            {
                "fields": [
                    "original_title",
                    "original_language",
                    "release_date",
                    "runtime",
                    "genre_list",
                ]
            },
        ),
        (
            "TMDB",
            {
                "fields": [
                    "tmdb_link",
                    "imdb_id",
                    "popularity",
                    "vote_count",
                    "vote_average",
                    "synced_at",
                ]
            },
        ),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("translations").distinct()

    @admin.display(description="")
    def poster(self, film):
        url = film.poster_url(size="w92")
        return format_html('<img src="{}" style="height:60px">', url) if url else ""

    @admin.display(description="TMDB")
    def tmdb_link(self, film):
        return format_html(
            '<a href="https://www.themoviedb.org/movie/{0}" target="_blank">{0}</a>',
            film.tmdb_id,
        )

    @admin.display(description="Genres")
    def genre_list(self, film):
        return ", ".join(str(g) for g in film.genres.all())


@admin.register(Genre)
class GenreAdmin(ReadOnlyAdminMixin, TranslatableAdmin, ModelAdmin):
    list_display = ["__str__", "tmdb_id"]


@admin.register(Person)
class PersonAdmin(ReadOnlyAdminMixin, ModelAdmin):
    list_display = ["name", "tmdb_id"]
    search_fields = ["name", "=tmdb_id"]


@admin.register(SkippedTmdbFilm)
class SkippedTmdbFilmAdmin(ReadOnlyAdminMixin, ModelAdmin):
    list_display = ["tmdb_id", "vote_count", "checked_at"]
    search_fields = ["=tmdb_id"]
