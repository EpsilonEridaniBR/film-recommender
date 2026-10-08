from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("films", "0002_search_title_language"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="filmsearchtitle",
            constraint=models.UniqueConstraint(
                fields=("film", "language", "text"), name="unique_film_language_text"
            ),
        ),
    ]
