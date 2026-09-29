import datetime as dt

from django.core.management.base import BaseCommand

from films import importer, tmdb
from films.models import Film


class Command(BaseCommand):
    help = (
        "Weekly catalogue refresh: re-fetch films TMDB reports as changed and add "
        "newly popular films. Never touches suggestions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=8,
            help="How many days of TMDB changes to pick up (max 14).",
        )
        parser.add_argument("--candidates", type=int, default=150_000)
        parser.add_argument("--min-votes", type=int, default=25)

    def handle(self, *args, **options):
        client = tmdb.TmdbClient()
        try:
            importer.sync_genres(client)

            end = dt.date.today()
            start = end - dt.timedelta(days=min(options["days"], 14))
            changed = client.changed_movie_ids(start, end)
            changed_existing = list(
                Film.objects.filter(tmdb_id__in=changed).values_list(
                    "tmdb_id", flat=True
                )
            )
            self.stdout.write(
                f"{len(changed)} films changed on TMDB, "
                f"{len(changed_existing)} of them in our catalogue."
            )

            candidates = tmdb.most_popular_ids(
                tmdb.download_export(), options["candidates"]
            )
            new_ids = importer.ids_needing_fetch(candidates)
            self.stdout.write(f"{len(new_ids)} new candidates to check.")

            stored, skipped, missing = importer.fetch_and_store(
                client,
                changed_existing + new_ids,
                options["min_votes"],
                log=self.stdout.write,
            )
        finally:
            client.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {stored} films stored, {skipped} below threshold, "
                f"{missing} not found."
            )
        )
