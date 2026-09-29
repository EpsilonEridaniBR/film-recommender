"""The rules for changing suggestions. Views and the admin go through here."""

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import audio as audio_processing
from .models import EditVote, Suggestion, SuggestionEdit

Action = SuggestionEdit.Action
Status = SuggestionEdit.Status

EXPLANATION_MAX_CHARS = 500


class EditError(Exception):
    pass


def check_edit(edit, live):
    """Raise EditError if `edit` can't be applied to the film's current
    suggestions, `live` (a dict of suggested film id -> Suggestion)."""
    if edit.proposed_film_id and edit.proposed_film_id == edit.source_film_id:
        raise EditError("A film can't be suggested for itself.")

    if edit.action == Action.ADD:
        if len(live) >= settings.SUGGESTIONS_PER_FILM:
            raise EditError("This film already has the maximum number of suggestions.")
        if edit.proposed_film_id in live:
            raise EditError("That film is already suggested.")
    else:
        if edit.replaced_film_id not in live:
            raise EditError("The suggestion being changed no longer exists.")
        # Replacing a film with itself is how an explanation gets updated.
        if (
            edit.action == Action.REPLACE
            and edit.proposed_film_id != edit.replaced_film_id
            and edit.proposed_film_id in live
        ):
            raise EditError("That film is already suggested.")


def live_suggestions(source_film_id, lock=False):
    queryset = Suggestion.objects.filter(source_film_id=source_film_id)
    if lock:
        queryset = queryset.select_for_update()
    return {s.suggested_film_id: s for s in queryset}


def _resolve(edit, status, note=""):
    edit.status = status
    edit.note = note
    edit.resolved_at = timezone.now()
    edit.save(update_fields=["status", "note", "resolved_at"])
    return edit


@transaction.atomic
def apply_edit(edit, status=Status.APPROVED):
    """Apply an edit to the live suggestions, mark it resolved, and reject any
    pending edits on the same film that no longer make sense."""
    live = live_suggestions(edit.source_film_id, lock=True)
    check_edit(edit, live)

    if edit.action in (Action.REPLACE, Action.REMOVE):
        live[edit.replaced_film_id].delete()
    if edit.action in (Action.ADD, Action.REPLACE):
        Suggestion.objects.create(
            source_film_id=edit.source_film_id,
            suggested_film_id=edit.proposed_film_id,
            explanation=edit.explanation,
            explanation_audio=edit.explanation_audio,
            audio_duration_ms=edit.audio_duration_ms,
            language=edit.language,
            approved_edit=edit,
        )
    _resolve(edit, status)
    reject_stale_edits(edit.source_film_id)
    return edit


def reject_stale_edits(source_film_id):
    live = live_suggestions(source_film_id)
    pending = SuggestionEdit.objects.select_for_update().filter(
        source_film_id=source_film_id, status=Status.PENDING
    )
    for other in pending:
        try:
            check_edit(other, live)
        except EditError as exc:
            _resolve(other, Status.REJECTED, f"Superseded: {exc}")


def submit_edit(
    user,
    source_film,
    action,
    proposed_film=None,
    replaced_film=None,
    explanation="",
    audio=None,
    language="en",
):
    """Propose a change. Adding to a film with room goes live immediately;
    replacing or removing goes to the review queue."""
    if not (user.is_active and user.can_moderate):
        raise EditError("Your account can't propose edits.")
    if not user.display_name:
        raise EditError("Choose a display name first.")

    explanation = (explanation or "").strip()
    if action == Action.REMOVE:
        explanation, audio = "", None
    elif bool(explanation) == bool(audio):
        raise EditError("Give either a written or a recorded explanation.")
    if len(explanation) > EXPLANATION_MAX_CHARS:
        raise EditError(
            f"Explanations can be at most {EXPLANATION_MAX_CHARS} characters."
        )

    if action != Action.ADD:
        pending = user.suggestion_edits.filter(status=Status.PENDING).count()
        if pending >= settings.MAX_PENDING_EDITS_PER_USER:
            raise EditError(
                f"You already have {pending} edits waiting for review. "
                "Withdraw one or wait for them to be settled."
            )

    edit = SuggestionEdit(
        source_film=source_film,
        action=action,
        proposed_film=proposed_film,
        replaced_film=replaced_film,
        explanation=explanation,
        language=language,
        proposer=user,
    )
    # Fail fast, before any audio work, if the edit can't apply right now.
    check_edit(edit, live_suggestions(source_film.pk))

    if audio:
        try:
            clip, duration_ms = audio_processing.process_upload(audio)
        except audio_processing.AudioError as exc:
            raise EditError(str(exc)) from exc
        edit.explanation_audio = clip
        edit.audio_duration_ms = duration_ms

    with transaction.atomic():
        edit.save()
        if action == Action.ADD:
            apply_edit(edit, status=Status.AUTO_APPROVED)
    return edit


def vote_counts(edit):
    return edit.votes.aggregate(
        approvals=Count("pk", filter=Q(approve=True)),
        rejections=Count("pk", filter=Q(approve=False)),
    )


@transaction.atomic
def vote(user, edit_id, approve, comment=""):
    """Record (or change) a vote; settle the edit once enough votes are in."""
    edit = SuggestionEdit.objects.select_for_update().get(pk=edit_id)
    if not (user.is_active and user.can_moderate):
        raise EditError("Your account can't vote on edits.")
    if not user.display_name:
        raise EditError("Choose a display name first.")
    if edit.status != Status.PENDING:
        raise EditError("This edit has already been settled.")
    if edit.proposer_id == user.pk:
        raise EditError("You can't vote on your own edit.")

    EditVote.objects.update_or_create(
        edit=edit, voter=user, defaults={"approve": approve, "comment": comment}
    )
    counts = vote_counts(edit)
    if counts["approvals"] >= settings.APPROVALS_REQUIRED:
        try:
            apply_edit(edit)
        except EditError as exc:
            _resolve(edit, Status.REJECTED, f"Couldn't be applied: {exc}")
    elif counts["rejections"] >= settings.REJECTIONS_REQUIRED:
        _resolve(edit, Status.REJECTED, "Rejected by moderators.")
    return edit


@transaction.atomic
def withdraw(user, edit_id):
    edit = SuggestionEdit.objects.select_for_update().get(pk=edit_id)
    if edit.proposer_id != user.pk:
        raise EditError("You can only withdraw your own edits.")
    if edit.status != Status.PENDING:
        raise EditError("This edit has already been settled.")
    return _resolve(edit, Status.WITHDRAWN)


@transaction.atomic
def staff_resolve(edit, approve):
    """Admin override: settle a pending edit without waiting for votes.
    Check the returned edit's status: an approval that can no longer be
    applied ends up rejected, with the reason in its note."""
    edit = SuggestionEdit.objects.select_for_update().get(pk=edit.pk)
    if edit.status != Status.PENDING:
        raise EditError("This edit has already been settled.")
    if not approve:
        return _resolve(edit, Status.REJECTED, "Rejected by an admin.")
    try:
        return apply_edit(edit)
    except EditError as exc:
        return _resolve(edit, Status.REJECTED, f"Couldn't be applied: {exc}")
