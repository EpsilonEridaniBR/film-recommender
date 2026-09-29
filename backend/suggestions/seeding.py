"""Seed suggestions from a spreadsheet of hand-picked recommendations.

Expected columns: Title, Year, Recommendation 1, Reason 1, ... Recommendation N,
Reason N. Other columns are ignored.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from films import importer
from films.models import Film

from .models import Suggestion, SuggestionEdit
from .services import EditError, apply_edit

TITLE_WITH_YEAR = re.compile(r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)$")


@dataclass
class SeedRow:
    line: int
    title: str
    year: int | None
    recommendations: list[tuple[str, str]]  # (title, reason)


def read_rows(path):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        table = list(sheet.iter_rows(values_only=True))
    else:
        with path.open(newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))

    header = [str(h or "").strip().lower() for h in table[0]]
    col = {name: i for i, name in enumerate(header)}
    pairs = []
    n = 1
    while f"recommendation {n}" in col:
        pairs.append((col[f"recommendation {n}"], col.get(f"reason {n}")))
        n += 1

    rows = []
    for line, values in enumerate(table[1:], start=2):
        title = _cell(values, col.get("title"))
        if not title:
            continue
        recommendations = [
            (_cell(values, rec_i), _cell(values, reason_i)) for rec_i, reason_i in pairs
        ]
        rows.append(
            SeedRow(
                line=line,
                title=title,
                year=_year(_cell(values, col.get("year"))),
                recommendations=[(t, r) for t, r in recommendations if t],
            )
        )
    return rows


def _cell(values, index):
    if index is None or index >= len(values) or values[index] is None:
        return ""
    return str(values[index]).strip()


def _year(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def split_title_year(text):
    """'Crash (1996)' -> ('Crash', 1996)."""
    match = TITLE_WITH_YEAR.match(text)
    if match:
        return match["title"], int(match["year"])
    return text, None


@dataclass
class Resolution:
    query: str
    tmdb_id: int | None = None
    matched_title: str = ""
    year: int | None = None
    exact: bool = False
    problem: str = ""


class Resolver:
    """Looks films up on TMDB, preferring exact title matches with the most votes."""

    def __init__(self, client):
        self.client = client
        self.cache = {}

    def resolve(self, text, year=None):
        key = (text, year)
        if key not in self.cache:
            self.cache[key] = self._resolve(text, year)
        return self.cache[key]

    def _resolve(self, text, year):
        title, year_in_title = split_title_year(text)
        year = year or year_in_title
        result = Resolution(query=text)
        if "?" in title:
            result.problem = "marked as uncertain in the spreadsheet"
            return result

        target = importer.normalise_title(title)
        candidates = self.client.search_movies(title)
        if year:
            candidates = [c for c in candidates if _near_year(c, year)]
        exact = [
            c
            for c in candidates
            if target
            in (
                importer.normalise_title(c.get("title") or ""),
                importer.normalise_title(c.get("original_title") or ""),
            )
        ]
        pool = exact or candidates
        if not pool:
            result.problem = "no match on TMDB"
            return result

        best = max(pool, key=lambda c: c.get("vote_count") or 0)
        result.tmdb_id = best["id"]
        result.matched_title = best.get("title") or ""
        result.year = _release_year(best)
        result.exact = bool(exact)
        return result


def _release_year(candidate):
    date = candidate.get("release_date") or ""
    return int(date[:4]) if date[:4].isdigit() else None


def _near_year(candidate, year):
    release_year = _release_year(candidate)
    return release_year is not None and abs(release_year - year) <= 1


def ensure_films(client, tmdb_ids):
    """Fetch any films not yet in the catalogue, whatever their vote count:
    hand-picked films always belong in the catalogue."""
    missing = set(tmdb_ids) - set(
        Film.objects.filter(tmdb_id__in=tmdb_ids).values_list("tmdb_id", flat=True)
    )
    if missing:
        importer.fetch_and_store(
            client, sorted(missing), min_votes=0, log=lambda _: None
        )
    return dict(Film.objects.filter(tmdb_id__in=tmdb_ids).values_list("tmdb_id", "pk"))


def create_seed_suggestion(source_pk, suggested_pk, reason):
    """Add a suggestion as an auto-approved edit with no proposer.
    Returns a short status string."""
    if Suggestion.objects.filter(
        source_film_id=source_pk, suggested_film_id=suggested_pk
    ).exists():
        return "already exists"
    edit = SuggestionEdit(
        source_film_id=source_pk,
        action=SuggestionEdit.Action.ADD,
        proposed_film_id=suggested_pk,
        explanation=reason,
        language="en",
    )
    try:
        edit.full_clean(exclude=["status"])
        edit.save()
        apply_edit(edit, status=SuggestionEdit.Status.AUTO_APPROVED)
    except EditError as exc:
        edit.delete()
        return f"skipped: {exc}"
    return "added"
