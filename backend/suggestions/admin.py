from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.text import Truncator
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from .models import EditVote, Report, Suggestion, SuggestionEdit
from .services import EditError, apply_edit, check_edit, staff_resolve


def audio_player(field):
    if not field:
        return "—"
    return format_html('<audio controls preload="none" src="{}"></audio>', field.url)


class SuggestionAddForm(forms.ModelForm):
    def clean(self):
        data = super().clean()
        source, suggested = data.get("source_film"), data.get("suggested_film")
        if source and suggested:
            live = {
                s.suggested_film_id: s
                for s in Suggestion.objects.filter(source_film=source)
            }
            edit = SuggestionEdit(
                source_film=source,
                action=SuggestionEdit.Action.ADD,
                proposed_film=suggested,
            )
            try:
                check_edit(edit, live)
            except EditError as exc:
                raise forms.ValidationError(str(exc))
        return data


@admin.register(Suggestion)
class SuggestionAdmin(ModelAdmin):
    form = SuggestionAddForm
    list_display = ["source_film", "suggested_film", "short_explanation", "has_audio"]
    search_fields = [
        "source_film__search_titles__text",
        "suggested_film__search_titles__text",
    ]
    autocomplete_fields = ["source_film", "suggested_film"]
    readonly_fields = ["approved_edit", "created_at", "audio"]
    fields = [
        "source_film",
        "suggested_film",
        "explanation",
        "explanation_audio",
        "audio",
        "audio_duration_ms",
        "language",
        "approved_edit",
        "created_at",
    ]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("source_film", "suggested_film")
            .prefetch_related(
                "source_film__translations", "suggested_film__translations"
            )
            .distinct()
        )

    def has_change_permission(self, request, obj=None):
        # Changes go through edits so there's always a history; add or delete instead.
        return obj is None and super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Adding a suggestion here records it as an auto-approved edit by you,
        with the same checks as community edits."""
        edit = SuggestionEdit(
            source_film=obj.source_film,
            action=SuggestionEdit.Action.ADD,
            proposed_film=obj.suggested_film,
            explanation=obj.explanation,
            explanation_audio=obj.explanation_audio,
            audio_duration_ms=obj.audio_duration_ms,
            language=obj.language,
            proposer=request.user,
        )
        edit.save()
        apply_edit(edit, status=SuggestionEdit.Status.AUTO_APPROVED)
        # Point the admin's redirect at the suggestion apply_edit created.
        obj.pk = Suggestion.objects.get(approved_edit=edit).pk

    @admin.display(description="Explanation")
    def short_explanation(self, suggestion):
        return Truncator(suggestion.explanation).chars(80)

    @admin.display(description="Audio", boolean=True)
    def has_audio(self, suggestion):
        return bool(suggestion.explanation_audio)

    @admin.display(description="Listen")
    def audio(self, suggestion):
        return audio_player(suggestion.explanation_audio)


class EditVoteInline(TabularInline):
    model = EditVote
    fields = ["voter", "approve", "comment", "created_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SuggestionEdit)
class SuggestionEditAdmin(ModelAdmin):
    list_display = [
        "source_film",
        "action",
        "replaced_film",
        "proposed_film",
        "proposer",
        "status",
        "created_at",
    ]
    list_filter = ["status", "action"]
    search_fields = ["source_film__search_titles__text", "proposer__display_name"]
    inlines = [EditVoteInline]
    actions = ["approve_edits", "reject_edits"]
    readonly_fields = [
        "source_film",
        "action",
        "replaced_film",
        "proposed_film",
        "explanation",
        "audio",
        "audio_duration_ms",
        "language",
        "proposer",
        "status",
        "note",
        "created_at",
        "resolved_at",
    ]
    exclude = ["explanation_audio"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("source_film", "replaced_film", "proposed_film", "proposer")
            .prefetch_related(
                "source_film__translations",
                "replaced_film__translations",
                "proposed_film__translations",
            )
            .distinct()
        )

    def has_add_permission(self, request):
        return False

    @admin.display(description="Audio")
    def audio(self, edit):
        return audio_player(edit.explanation_audio)

    def _resolve(self, request, queryset, approve):
        done = failed = 0
        for edit in queryset.filter(status=SuggestionEdit.Status.PENDING):
            try:
                edit = staff_resolve(edit, approve)
            except EditError:
                continue  # settled by someone else in the meantime
            if approve and edit.status == SuggestionEdit.Status.REJECTED:
                failed += 1
                self.message_user(
                    request, f"{edit}: {edit.note}", level=messages.WARNING
                )
            else:
                done += 1
        verb = "approved" if approve else "rejected"
        self.message_user(request, f"{done} edit(s) {verb}.")

    @action(description="Approve selected pending edits")
    def approve_edits(self, request, queryset):
        self._resolve(request, queryset, approve=True)

    @action(description="Reject selected pending edits")
    def reject_edits(self, request, queryset):
        self._resolve(request, queryset, approve=False)


@admin.register(Report)
class ReportAdmin(ModelAdmin):
    list_display = ["suggestion", "reporter", "short_reason", "resolved", "created_at"]
    list_filter = ["resolved"]
    readonly_fields = ["suggestion", "reporter", "reason", "created_at", "audio"]
    fields = ["suggestion", "audio", "reporter", "reason", "created_at", "resolved"]
    actions = ["remove_suggestions", "dismiss"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Reason")
    def short_reason(self, report):
        return Truncator(report.reason).chars(80)

    @admin.display(description="Audio")
    def audio(self, report):
        return audio_player(report.suggestion.explanation_audio)

    @action(description="Remove the reported suggestions")
    def remove_suggestions(self, request, queryset):
        """Removes via a recorded edit, so the change shows in the film's history."""
        removed = 0
        for suggestion in Suggestion.objects.filter(reports__in=queryset).distinct():
            edit = SuggestionEdit.objects.create(
                source_film_id=suggestion.source_film_id,
                action=SuggestionEdit.Action.REMOVE,
                replaced_film_id=suggestion.suggested_film_id,
                proposer=request.user,
                note="Removed after being reported.",
            )
            apply_edit(edit)
            removed += 1
        self.message_user(request, f"{removed} suggestion(s) removed.")

    @action(description="Dismiss selected reports")
    def dismiss(self, request, queryset):
        count = queryset.update(resolved=True)
        self.message_user(request, f"{count} report(s) dismissed.")
