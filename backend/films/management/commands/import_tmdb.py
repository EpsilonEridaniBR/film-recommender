from django.core.management.base import BaseCommand

from films import importer, tmdb


class Command(BaseCommand):
    help = (
        "Build the film catalogue from TMDB: take the most popular films from "
        "TMDB's daily export, fetch their details, and keep those with enough votes. "
        "Safe to re-run; it resumes where it left off."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--candidates",
            type=int,
            default=150_000,
            help="How many of the most popular TMDB films to consider.",
        )
        parser.add_argument(
            "--min-votes",
            type=int,
            default=25,
            help="Minimum TMDB vote count for a film to enter the catalogue.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Only fetch this many films (for testing).",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Re-fetch films that are already in the catalogue.",
        )

    def handle(self, *args, **options):
        client = tmdb.TmdbClient()
        try:
            count = importer.sync_genres(client)
            self.stdout.write(f"Synced {count} genres.")

            self.stdout.write("Downloading TMDB daily export...")
            candidates = tmdb.most_popular_ids(
                tmdb.download_export(), options["candidates"]
            )
            to_fetch = importer.ids_needing_fetch(
                candidates, refresh=options["refresh"]
            )
            if options["limit"]:
                to_fetch = to_fetch[: options["limit"]]
            self.stdout.write(
                f"{len(candidates)} candidates, {len(to_fetch)} to fetch."
            )

            stored, skipped, missing = importer.fetch_and_store(
                client, to_fetch, options["min_votes"], log=self.stdout.write
            )
        finally:
            client.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {stored} films stored, {skipped} below threshold, "
                f"{missing} not found."
            )
        )
