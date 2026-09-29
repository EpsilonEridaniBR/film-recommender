from suggestions import seeding
from suggestions.models import Suggestion, SuggestionEdit


def test_read_rows_from_csv(tmp_path):
    path = tmp_path / "seed.csv"
    path.write_text(
        "Title,Year,Description,Initials,Recommendation 1,Reason 1,"
        "Recommendation 2,Reason 2\n"
        "Casablanca,1942,,AJ,Citizen Kane,Gateway film,Play It Again Sam,\n"
        "Empty Row,1999,,,,,,\n"
    )

    rows = seeding.read_rows(path)

    assert rows[0].title == "Casablanca"
    assert rows[0].year == 1942
    assert rows[0].recommendations == [
        ("Citizen Kane", "Gateway film"),
        ("Play It Again Sam", ""),
    ]
    assert rows[1].recommendations == []


def test_split_title_year():
    assert seeding.split_title_year("Crash (1996)") == ("Crash", 1996)
    assert seeding.split_title_year("1917") == ("1917", None)


class FakeSearchClient:
    def __init__(self, results):
        self.results = results

    def search_movies(self, query, year=None):
        return self.results


def result(tmdb_id, title, year, votes):
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "release_date": f"{year}-01-01",
        "vote_count": votes,
    }


def test_resolver_prefers_exact_title_with_most_votes():
    client = FakeSearchClient(
        [
            result(1, "Crash Landing", 2020, 9000),
            result(2, "Crash", 2004, 5000),
            result(3, "Crash", 1996, 2000),
        ]
    )
    resolver = seeding.Resolver(client)

    assert resolver.resolve("Crash").tmdb_id == 2
    assert resolver.resolve("Crash (1996)").tmdb_id == 3
    assert resolver.resolve("Crash", year=1997).tmdb_id == 3


def test_resolver_falls_back_to_best_fuzzy_match():
    client = FakeSearchClient([result(1, "Rain Man", 1988, 7000)])
    resolution = seeding.Resolver(client).resolve("Rainman")
    assert (resolution.tmdb_id, resolution.exact) == (1, False)


def test_resolver_skips_uncertain_titles():
    resolution = seeding.Resolver(FakeSearchClient([])).resolve("Under Suspicion?")
    assert resolution.tmdb_id is None
    assert "uncertain" in resolution.problem


def test_create_seed_suggestion_is_idempotent(films):
    source, suggested = films["Casablanca"].pk, films["Arrival"].pk

    assert seeding.create_seed_suggestion(source, suggested, "Reason") == "added"
    assert seeding.create_seed_suggestion(source, suggested, "Reason") == (
        "already exists"
    )

    edit = SuggestionEdit.objects.get()
    assert edit.status == SuggestionEdit.Status.AUTO_APPROVED
    assert edit.proposer is None
    assert Suggestion.objects.get().approved_edit == edit
