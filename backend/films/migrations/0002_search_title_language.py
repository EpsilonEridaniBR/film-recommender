import re
import unicodedata

from django.db import migrations, models

ORIGINAL = "original"
BATCH_SIZE = 2000


def normalise_title(text):
    # A frozen copy of films.importer.normalise_title, so this migration keeps
    # working if that function changes later.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w]+", " ", text.lower())
    return " ".join(text.split())


def rebuild_search_titles(apps, schema_editor):
    """Recreate every search title with its language, from data already in the
    database (original titles and translations), without calling TMDB."""
    Film = apps.get_model("films", "Film")
    FilmTranslation = apps.get_model("films", "FilmTranslation")
    FilmSearchTitle = apps.get_model("films", "FilmSearchTitle")

    FilmSearchTitle.objects.all().delete()
    film_ids = list(Film.objects.order_by("pk").values_list("pk", flat=True))
    for start in range(0, len(film_ids), BATCH_SIZE):
        batch = film_ids[start : start + BATCH_SIZE]
        titles = {
            (pk, ORIGINAL, title)
            for pk, title in Film.objects.filter(pk__in=batch).values_list(
                "pk", "original_title"
            )
        } | set(
            FilmTranslation.objects.filter(master_id__in=batch).values_list(
                "master_id", "language_code", "title"
            )
        )
        rows = {}
        for film_id, language, title in titles:
            text = normalise_title(title)
            if text:
                rows[(film_id, language, text)] = FilmSearchTitle(
                    film_id=film_id,
                    language=language,
                    title=title[:500],
                    text=text[:500],
                )
        FilmSearchTitle.objects.bulk_create(rows.values())


class Migration(migrations.Migration):

    dependencies = [
        ("films", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="filmsearchtitle",
            name="unique_film_text",
        ),
        migrations.AddField(
            model_name="filmsearchtitle",
            name="language",
            field=models.CharField(default="", max_length=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="filmsearchtitle",
            name="title",
            field=models.CharField(default="", max_length=500),
            preserve_default=False,
        ),
        # The new unique constraint is added in 0003: Postgres can't alter the
        # table in the same transaction as this bulk rewrite.
        migrations.RunPython(rebuild_search_titles, migrations.RunPython.noop),
    ]
