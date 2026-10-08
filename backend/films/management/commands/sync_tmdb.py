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
        parser.add_argument(
            "--recheck-popular",
            type=int,
            default=10_000,
            help=(
                "Re-check films that were below --min-votes if they're now among "
                "this many most popular on TMDB (e.g. new releases), however "
                "recently they were checked."
            ),
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "Re-fetch every film already in the catalogue, not just changed "
                "ones (e.g. after adding a field to the import)."
            ),
        )
        parser.add_argument(
            "--ids",
            type=int,
            nargs="+",
            metavar="TMDB_ID",
            help=(
                "Fetch just these films (still subject to --min-votes) and nothing "
                "else, e.g. a new release you want straight away."
            ),
        )

    def handle(self, *args, **options):
        client = tmdb.TmdbClient()
        try:
            importer.sync_genres(client)
            if options["ids"]:
                tmdb_ids = options["ids"]
                self.stdout.write(f"Fetching {len(tmdb_ids)} films.")
            else:
                tmdb_ids = self.ids_to_sync(client, options)

            stored, skipped, missing = importer.fetch_and_store(
                client,
                tmdb_ids,
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

    def ids_to_sync(self, client, options):
        if options["all"]:
            changed = set()
            changed_existing = list(
                Film.objects.order_by("-vote_count").values_list("tmdb_id", flat=True)
            )
            self.stdout.write(f"Re-fetching all {len(changed_existing)} films.")
        else:
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

        recheck = importer.skipped_to_recheck(
            changed | set(candidates[: options["recheck_popular"]])
        )
        self.stdout.write(
            f"{len(recheck)} films below the threshold before are changed or "
            "popular on TMDB; checking them again."
        )
        # Most important first, without duplicates.
        return list(dict.fromkeys(changed_existing + recheck + new_ids))
