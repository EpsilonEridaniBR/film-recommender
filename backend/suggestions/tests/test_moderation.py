import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from suggestions import audio, services
from suggestions.models import Suggestion, SuggestionEdit

Action = SuggestionEdit.Action
Status = SuggestionEdit.Status


def seed(films, source, *titles):
    for title in titles:
        services.apply_edit(
            SuggestionEdit.objects.create(
                source_film=films[source],
                action=Action.ADD,
                proposed_film=films[title],
                explanation="seed",
            )
        )


def live(films, source):
    return sorted(
        s.suggested_film.safe_translation_getter("title")
        for s in Suggestion.objects.filter(source_film=films[source])
    )


def replace(user, films, old, new, source="Casablanca"):
    return services.submit_edit(
        user,
        films[source],
        Action.REPLACE,
        proposed_film=films[new],
        replaced_film=films[old],
        explanation=f"{new} is better",
    )


# --- Submitting -------------------------------------------------------------


def test_adding_to_a_film_with_room_goes_live_immediately(films, users):
    edit = services.submit_edit(
        users["alice"],
        films["Casablanca"],
        Action.ADD,
        proposed_film=films["Arrival"],
        explanation="Both about waiting",
    )

    assert edit.status == Status.AUTO_APPROVED
    assert live(films, "Casablanca") == ["Arrival"]
    assert Suggestion.objects.get().approved_edit == edit


def test_replacing_goes_to_the_queue(films, users):
    seed(films, "Casablanca", "Arrival")

    edit = replace(users["alice"], films, "Arrival", "Up")

    assert edit.status == Status.PENDING
    assert live(films, "Casablanca") == ["Arrival"]


def test_removing_goes_to_the_queue_and_ignores_explanations(films, users):
    seed(films, "Casablanca", "Arrival")

    edit = services.submit_edit(
        users["alice"],
        films["Casablanca"],
        Action.REMOVE,
        replaced_film=films["Arrival"],
        explanation="ignored",
    )

    assert edit.status == Status.PENDING
    assert edit.explanation == ""


@pytest.mark.parametrize("explanation, with_audio", [("", False), ("Text", True)])
def test_needs_exactly_one_explanation(films, users, clip, explanation, with_audio):
    with pytest.raises(services.EditError, match="either a written or a recorded"):
        services.submit_edit(
            users["alice"],
            films["Casablanca"],
            Action.ADD,
            proposed_film=films["Arrival"],
            explanation=explanation,
            audio=clip() if with_audio else None,
        )


def test_explanation_length_limit(films, users):
    with pytest.raises(services.EditError, match="at most 500"):
        services.submit_edit(
            users["alice"],
            films["Casablanca"],
            Action.ADD,
            proposed_film=films["Arrival"],
            explanation="x" * 501,
        )


def test_impossible_edits_are_refused_up_front(films, users):
    with pytest.raises(services.EditError, match="no longer exists"):
        replace(users["alice"], films, "Arrival", "Up")
    assert not SuggestionEdit.objects.exists()


def test_pending_edit_cap(films, users, settings):
    settings.MAX_PENDING_EDITS_PER_USER = 2
    seed(films, "Casablanca", "Arrival")
    replace(users["alice"], films, "Arrival", "Up")
    second = replace(users["alice"], films, "Arrival", "Zodiac")

    with pytest.raises(services.EditError, match="already have 2 edits"):
        replace(users["alice"], films, "Arrival", "The Matrix")

    services.withdraw(users["alice"], second.pk)
    replace(users["alice"], films, "Arrival", "The Matrix")  # a slot freed up


def test_adds_do_not_count_towards_the_cap(films, users, settings):
    settings.MAX_PENDING_EDITS_PER_USER = 1
    seed(films, "Casablanca", "Arrival")
    replace(users["alice"], films, "Arrival", "Up")

    services.submit_edit(
        users["alice"],
        films["Zodiac"],
        Action.ADD,
        proposed_film=films["Up"],
        explanation="Still allowed",
    )


def test_banned_users_cannot_submit_or_vote(films, users):
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")
    users["bob"].can_moderate = False
    users["bob"].save()

    with pytest.raises(services.EditError, match="can't propose"):
        replace(users["bob"], films, "Arrival", "Zodiac")
    with pytest.raises(services.EditError, match="can't vote"):
        services.vote(users["bob"], edit.pk, approve=True)


# --- Voting -----------------------------------------------------------------


def test_two_approvals_apply_the_edit(films, users):
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")

    services.vote(users["bob"], edit.pk, approve=True)
    edit.refresh_from_db()
    assert edit.status == Status.PENDING

    services.vote(users["carol"], edit.pk, approve=True)
    edit.refresh_from_db()
    assert edit.status == Status.APPROVED
    assert live(films, "Casablanca") == ["Up"]


def test_two_rejections_reject_the_edit(films, users):
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")

    services.vote(users["bob"], edit.pk, approve=False)
    services.vote(users["carol"], edit.pk, approve=False)

    edit.refresh_from_db()
    assert edit.status == Status.REJECTED
    assert edit.note == "Rejected by moderators."
    assert live(films, "Casablanca") == ["Arrival"]


def test_votes_can_change_until_settled(films, users):
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")

    services.vote(users["bob"], edit.pk, approve=False)
    services.vote(users["bob"], edit.pk, approve=True)
    assert edit.votes.get().approve is True

    services.vote(users["carol"], edit.pk, approve=True)
    with pytest.raises(services.EditError, match="already been settled"):
        services.vote(users["bob"], edit.pk, approve=False)


def test_cannot_vote_on_own_edit(films, users):
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")
    with pytest.raises(services.EditError, match="your own"):
        services.vote(users["alice"], edit.pk, approve=True)


def test_applying_an_edit_rejects_conflicting_pending_edits(films, users):
    seed(films, "Casablanca", "Arrival")
    winner = replace(users["alice"], films, "Arrival", "Up")
    loser = replace(users["bob"], films, "Arrival", "Zodiac")

    services.vote(users["carol"], winner.pk, approve=True)
    services.vote(users["dave"], winner.pk, approve=True)

    loser.refresh_from_db()
    assert loser.status == Status.REJECTED
    assert loser.note.startswith("Superseded:")


def test_approved_edit_that_no_longer_applies_is_rejected(films, users, settings):
    settings.SUGGESTIONS_PER_FILM = 1
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")
    # Someone removes the suggestion behind the queue's back.
    Suggestion.objects.all().delete()

    services.vote(users["bob"], edit.pk, approve=True)
    services.vote(users["carol"], edit.pk, approve=True)

    edit.refresh_from_db()
    assert edit.status == Status.REJECTED
    assert "Couldn't be applied" in edit.note


def test_withdraw_only_own_pending_edits(films, users):
    seed(films, "Casablanca", "Arrival")
    edit = replace(users["alice"], films, "Arrival", "Up")

    with pytest.raises(services.EditError, match="your own"):
        services.withdraw(users["bob"], edit.pk)
    assert services.withdraw(users["alice"], edit.pk).status == Status.WITHDRAWN
    with pytest.raises(services.EditError, match="already been settled"):
        services.withdraw(users["alice"], edit.pk)


# --- Audio ------------------------------------------------------------------


def test_audio_explanations_are_transcoded(films, users, clip, media):
    edit = services.submit_edit(
        users["alice"],
        films["Casablanca"],
        Action.ADD,
        proposed_film=films["Arrival"],
        audio=clip(seconds=2),
    )

    assert edit.explanation == ""
    assert edit.explanation_audio.name.endswith(".m4a")
    assert 1900 <= edit.audio_duration_ms <= 2200
    suggestion = Suggestion.objects.get()
    assert suggestion.explanation_audio.name == edit.explanation_audio.name


def test_audio_too_long(films, users, clip, media, settings):
    settings.AUDIO_MAX_SECONDS = 1
    with pytest.raises(services.EditError, match="at most 1 seconds"):
        services.submit_edit(
            users["alice"],
            films["Casablanca"],
            Action.ADD,
            proposed_film=films["Arrival"],
            audio=clip(seconds=3),
        )


def test_audio_too_big(films, users, clip, media, settings):
    settings.AUDIO_MAX_BYTES = 1000
    with pytest.raises(services.EditError, match="at most 0 MB"):
        services.submit_edit(
            users["alice"],
            films["Casablanca"],
            Action.ADD,
            proposed_film=films["Arrival"],
            audio=clip(seconds=2),
        )


def test_non_audio_upload(media):
    upload = SimpleUploadedFile("notes.m4a", b"definitely not audio")
    with pytest.raises(audio.AudioError):
        audio.process_upload(upload)


def test_cleanup_removes_old_rejected_audio(films, users, clip, media):
    seed(films, "Casablanca", "Arrival")
    edit = services.submit_edit(
        users["alice"],
        films["Casablanca"],
        Action.REPLACE,
        proposed_film=films["Up"],
        replaced_film=films["Arrival"],
        audio=clip(),
    )
    services.withdraw(users["alice"], edit.pk)
    path = media / edit.explanation_audio.name
    assert path.exists()

    call_command("cleanup_audio", days=0)

    edit.refresh_from_db()
    assert not path.exists()
    assert edit.explanation_audio.name == ""
    assert edit.explanation == "(audio clip deleted)"


def test_users_need_a_display_name(films, django_user_model):
    nameless = django_user_model.objects.create_user(username="nameless")
    with pytest.raises(services.EditError, match="display name"):
        services.submit_edit(
            nameless,
            films["Casablanca"],
            Action.ADD,
            proposed_film=films["Arrival"],
            explanation="x",
        )
