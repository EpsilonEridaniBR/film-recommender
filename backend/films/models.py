from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from parler.models import TranslatableModel, TranslatedFields

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"


def tmdb_image_url(path, size):
    return f"{TMDB_IMAGE_BASE}{size}{path}" if path else None


class Genre(TranslatableModel):
    tmdb_id = models.PositiveIntegerField(unique=True)
    translations = TranslatedFields(name=models.CharField(max_length=100))

    def __str__(self):
        return self.safe_translation_getter("name", any_language=True) or str(
            self.tmdb_id
        )


class Person(models.Model):
    tmdb_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255)
    profile_path = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "people"

    def __str__(self):
        return self.name


class Film(TranslatableModel):
    tmdb_id = models.PositiveIntegerField(unique=True)
    imdb_id = models.CharField(max_length=20, blank=True)
    original_title = models.CharField(max_length=500)
    original_language = models.CharField(max_length=10, blank=True)
    release_date = models.DateField(null=True, blank=True)
    runtime = models.PositiveSmallIntegerField(null=True, blank=True)
    poster_path = models.CharField(max_length=100, blank=True)
    backdrop_path = models.CharField(max_length=100, blank=True)
    popularity = models.FloatField(default=0)
    vote_count = models.PositiveIntegerField(default=0)
    vote_average = models.FloatField(default=0)
    genres = models.ManyToManyField(Genre, related_name="films", blank=True)
    synced_at = models.DateTimeField(
        help_text="When this film was last fetched from TMDB."
    )

    translations = TranslatedFields(
        title=models.CharField(max_length=500),
        overview=models.TextField(blank=True),
        tagline=models.CharField(max_length=500, blank=True),
    )

    class Meta:
        indexes = [models.Index(fields=["-vote_count"])]

    def __str__(self):
        title = self.safe_translation_getter("title", any_language=True)
        year = f" ({self.release_date.year})" if self.release_date else ""
        return f"{title or self.original_title}{year}"

    def poster_url(self, size="w500"):
        return tmdb_image_url(self.poster_path, size)

    def backdrop_url(self, size="w1280"):
        return tmdb_image_url(self.backdrop_path, size)


class Credit(models.Model):
    class Role(models.TextChoices):
        DIRECTOR = "director", "Director"
        CAST = "cast", "Cast"

    film = models.ForeignKey(Film, on_delete=models.CASCADE, related_name="credits")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="credits")
    role = models.CharField(max_length=20, choices=Role.choices)
    character = models.CharField(max_length=500, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["role", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["film", "person", "role"], name="unique_film_person_role"
            )
        ]


class FilmSearchTitle(models.Model):
    """One of a film's titles (its original title, its title in a catalogue
    language, or an alternative title), with a normalised copy for searching."""

    # `language` value for the film's original title.
    ORIGINAL = "original"
    # Alternative titles (e.g. "Seven" for Se7en) are stored as "alt-<language>".
    ALTERNATIVE_PREFIX = "alt-"

    @classmethod
    def alternative(cls, language):
        return f"{cls.ALTERNATIVE_PREFIX}{language}"

    @classmethod
    def is_alternative_language(cls, language):
        return language.startswith(cls.ALTERNATIVE_PREFIX)

    film = models.ForeignKey(
        Film, on_delete=models.CASCADE, related_name="search_titles"
    )
    language = models.CharField(max_length=10)
    title = models.CharField(max_length=500)
    text = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["film", "language", "text"], name="unique_film_language_text"
            )
        ]
        indexes = [
            GinIndex(OpClass("text", name="gin_trgm_ops"), name="filmsearchtitle_trgm"),
            models.Index(
                OpClass("text", name="varchar_pattern_ops"),
                name="filmsearchtitle_prefix",
            ),
        ]


class SkippedTmdbFilm(models.Model):
    """A TMDB film that was fetched but didn't meet the catalogue threshold.
    Remembered so imports and syncs don't re-fetch it every run."""

    tmdb_id = models.PositiveIntegerField(unique=True)
    vote_count = models.PositiveIntegerField(default=0)
    checked_at = models.DateTimeField()
