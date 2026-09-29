import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from films.models import Film

# Exactly one of a text explanation or an audio clip.
HAS_TEXT = ~Q(explanation="")
HAS_AUDIO = ~Q(explanation_audio="")
ONE_EXPLANATION = (HAS_TEXT & ~HAS_AUDIO) | (~HAS_TEXT & HAS_AUDIO)


def audio_upload_path(instance, filename):
    # Random names: never trust or expose the uploaded filename.
    return f"audio/{uuid.uuid4().hex}.m4a"


class Explanation(models.Model):
    explanation = models.TextField(blank=True)
    explanation_audio = models.FileField(upload_to=audio_upload_path, blank=True)
    audio_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES, default="en")

    class Meta:
        abstract = True


class Suggestion(Explanation):
    """A live suggestion: 'if you liked source_film, watch suggested_film'.
    Suggestions have no order; they're shown alphabetically by title."""

    source_film = models.ForeignKey(
        Film, on_delete=models.CASCADE, related_name="suggestions"
    )
    suggested_film = models.ForeignKey(
        Film, on_delete=models.CASCADE, related_name="suggested_by"
    )
    approved_edit = models.ForeignKey(
        "SuggestionEdit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_film", "suggested_film"],
                name="unique_suggestion_per_film",
            ),
            models.CheckConstraint(
                condition=~Q(source_film=models.F("suggested_film")),
                name="suggestion_not_self",
            ),
            models.CheckConstraint(
                condition=ONE_EXPLANATION, name="suggestion_one_explanation"
            ),
        ]

    def __str__(self):
        return f"{self.source_film} → {self.suggested_film}"


class SuggestionEdit(Explanation):
    """A proposed change to a film's suggestions. Approved edits double as the
    history of how each film's suggestions came to be."""

    class Action(models.TextChoices):
        ADD = "add", "Add"
        REPLACE = "replace", "Replace"
        REMOVE = "remove", "Remove"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        AUTO_APPROVED = "auto_approved", "Auto-approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    source_film = models.ForeignKey(
        Film, on_delete=models.CASCADE, related_name="suggestion_edits"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    # For replace/remove: the currently suggested film being taken out.
    replaced_film = models.ForeignKey(
        Film, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # For add/replace: the film being suggested.
    proposed_film = models.ForeignKey(
        Film, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # Null for seeded suggestions, and kept (as null) if the account is deleted.
    proposer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestion_edits",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Why it was rejected or auto-resolved, e.g. superseded by another edit.
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        action="add",
                        proposed_film__isnull=False,
                        replaced_film__isnull=True,
                    )
                    & ONE_EXPLANATION
                )
                | (
                    Q(
                        action="replace",
                        proposed_film__isnull=False,
                        replaced_film__isnull=False,
                    )
                    & ONE_EXPLANATION
                )
                | Q(
                    action="remove",
                    proposed_film__isnull=True,
                    replaced_film__isnull=False,
                    explanation="",
                    explanation_audio="",
                ),
                name="suggestion_edit_valid_action",
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} on {self.source_film} ({self.status})"


class EditVote(models.Model):
    edit = models.ForeignKey(
        SuggestionEdit, on_delete=models.CASCADE, related_name="votes"
    )
    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="edit_votes"
    )
    approve = models.BooleanField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["edit", "voter"], name="one_vote_per_edit")
        ]


class Report(models.Model):
    """A user flagging a live suggestion as inappropriate."""

    suggestion = models.ForeignKey(
        Suggestion, on_delete=models.CASCADE, related_name="reports"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["suggestion", "reporter"], name="one_report_per_user"
            )
        ]
