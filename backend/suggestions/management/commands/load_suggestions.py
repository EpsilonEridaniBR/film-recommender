from django.core.management.base import BaseCommand
from django.db import transaction

from films.tmdb import TmdbClient
from suggestions import seeding


class Command(BaseCommand):
    help = (
        "Seed suggestions from a spreadsheet (.xlsx or .csv) with columns Title, "
        "Year, Recommendation 1, Reason 1, ... Only recommendations with a reason "
        "are imported. Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how each title resolves without changing anything.",
        )

    def handle(self, path, dry_run=False, **options):
        rows = seeding.read_rows(path)
        client = TmdbClient()
        resolver = seeding.Resolver(client)
        counts = {}
        problems = []
        fuzzy = []

        def note(status):
            counts[status] = counts.get(status, 0) + 1

        try:
            for row in rows:
                with_reason = [(t, r) for t, r in row.recommendations if r]
                if not with_reason:
                    continue
                source = resolver.resolve(row.title, row.year)
                if not source.tmdb_id:
                    problems.append(
                        f"row {row.line}: {row.title} ({row.year}) - {source.problem}"
                    )
                    note("source not found")
                    continue
                if not source.exact:
                    fuzzy.append(
                        f"row {row.line}: '{row.title}' -> {source.matched_title} ({source.year})"
                    )

                for title, reason in with_reason:
                    rec = resolver.resolve(title)
                    if not rec.tmdb_id:
                        problems.append(
                            f"row {row.line}: {row.title} -> '{title}' - {rec.problem}"
                        )
                        note("recommendation not found")
                        continue
                    if not rec.exact:
                        fuzzy.append(
                            f"row {row.line}: '{title}' -> {rec.matched_title} ({rec.year})"
                        )
                    self.stdout.write(
                        f"  {source.matched_title} ({source.year}) -> "
                        f"{rec.matched_title} ({rec.year})"
                    )
                    if dry_run:
                        note("would add")
                        continue
                    with transaction.atomic():
                        pks = seeding.ensure_films(
                            client, [source.tmdb_id, rec.tmdb_id]
                        )
                        status = seeding.create_seed_suggestion(
                            pks[source.tmdb_id], pks[rec.tmdb_id], reason
                        )
                    note(status)
                    if status.startswith("skipped"):
                        problems.append(
                            f"row {row.line}: {row.title} -> '{title}' - {status}"
                        )
        finally:
            client.close()

        if fuzzy:
            self.stdout.write(
                self.style.WARNING("\nNot an exact title match - please check:")
            )
            for line in fuzzy:
                self.stdout.write(f"  {line}")
        if problems:
            self.stdout.write(self.style.WARNING("\nNot imported:"))
            for line in problems:
                self.stdout.write(f"  {line}")
        self.stdout.write(
            self.style.SUCCESS("\n" + ", ".join(f"{n} {s}" for s, n in counts.items()))
        )
