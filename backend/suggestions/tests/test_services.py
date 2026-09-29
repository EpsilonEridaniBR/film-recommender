import pytest
from django.db import IntegrityError

from suggestions.models import Suggestion, SuggestionEdit
from suggestions.services import EditError, apply_edit

Action = SuggestionEdit.Action


def make_edit(source, action, proposed=None, replaced=None, explanation="Because"):
    return SuggestionEdit.objects.create(
        source_film=source,
        action=action,
        proposed_film=proposed,
        replaced_film=replaced,
        explanation="" if action == Action.REMOVE else explanation,
    )


def suggested_titles(film):
    return sorted(
        s.suggested_film.safe_translation_getter("title")
        for s in Suggestion.objects.filter(source_film=film)
    )


def test_add_replace_remove(films):
    casablanca = films["Casablanca"]

    apply_edit(make_edit(casablanca, Action.ADD, proposed=films["Arrival"]))
    apply_edit(make_edit(casablanca, Action.ADD, proposed=films["Up"]))
    assert suggested_titles(casablanca) == ["Arrival", "Up"]

    edit = make_edit(
        casablanca, Action.REPLACE, proposed=films["Zodiac"], replaced=films["Up"]
    )
    apply_edit(edit)
    assert suggested_titles(casablanca) == ["Arrival", "Zodiac"]
    edit.refresh_from_db()
    assert edit.status == SuggestionEdit.Status.APPROVED
    assert edit.resolved_at is not None

    apply_edit(make_edit(casablanca, Action.REMOVE, replaced=films["Arrival"]))
    assert suggested_titles(casablanca) == ["Zodiac"]


def test_replacing_a_film_with_itself_updates_the_explanation(films):
    casablanca = films["Casablanca"]
    apply_edit(make_edit(casablanca, Action.ADD, proposed=films["Arrival"]))

    apply_edit(
        make_edit(
            casablanca,
            Action.REPLACE,
            proposed=films["Arrival"],
            replaced=films["Arrival"],
            explanation="A better reason",
        )
    )

    assert Suggestion.objects.get().explanation == "A better reason"


def test_cannot_exceed_suggestions_per_film(films, settings):
    settings.SUGGESTIONS_PER_FILM = 2
    casablanca = films["Casablanca"]
    apply_edit(make_edit(casablanca, Action.ADD, proposed=films["Arrival"]))
    apply_edit(make_edit(casablanca, Action.ADD, proposed=films["Up"]))

    with pytest.raises(EditError, match="maximum"):
        apply_edit(make_edit(casablanca, Action.ADD, proposed=films["Zodiac"]))


@pytest.mark.parametrize(
    "setup, action, proposed, replaced, message",
    [
        (["Arrival"], Action.ADD, "Arrival", None, "already suggested"),
        ([], Action.ADD, "Casablanca", None, "itself"),
        ([], Action.REMOVE, None, "Arrival", "no longer exists"),
        (["Arrival", "Up"], Action.REPLACE, "Up", "Arrival", "already suggested"),
    ],
)
def test_invalid_edits(films, setup, action, proposed, replaced, message):
    casablanca = films["Casablanca"]
    for title in setup:
        apply_edit(make_edit(casablanca, Action.ADD, proposed=films[title]))

    edit = make_edit(
        casablanca,
        action,
        proposed=films.get(proposed),
        replaced=films.get(replaced),
    )
    with pytest.raises(EditError, match=message):
        apply_edit(edit)


@pytest.mark.django_db
def test_suggestion_requires_exactly_one_explanation(films):
    with pytest.raises(IntegrityError):
        Suggestion.objects.create(
            source_film=films["Casablanca"],
            suggested_film=films["Arrival"],
            explanation="",
        )


@pytest.mark.django_db
def test_edit_action_must_be_consistent(films):
    with pytest.raises(IntegrityError):
        SuggestionEdit.objects.create(
            source_film=films["Casablanca"],
            action=Action.ADD,
            explanation="Missing the proposed film",
        )
