from django.core.management.base import BaseCommand
from django.db import transaction

from films.importer import normalise_title
from films.models import FilmSearchTitle

BATCH_SIZE = 5000


class Command(BaseCommand):
    help = (
        "Recompute the normalised search text of every film title. Run after "
        "changing films.importer.normalise_title."
    )

    def handle(self, *args, **options):
        changed = 0
        titles = FilmSearchTitle.objects.order_by("pk").only("pk", "title", "text")
        batch = []
        for row in titles.iterator(chunk_size=BATCH_SIZE):
            text = normalise_title(row.title)[:500]
            if text and text != row.text:
                row.text = text
                batch.append(row)
            if len(batch) >= BATCH_SIZE:
                changed += self.save(batch)
                batch = []
        changed += self.save(batch)
        self.stdout.write(self.style.SUCCESS(f"Updated {changed} search titles."))

    @transaction.atomic
    def save(self, rows):
        FilmSearchTitle.objects.bulk_update(rows, ["text"])
        return len(rows)
