import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from suggestions.models import SuggestionEdit


class Command(BaseCommand):
    help = "Delete audio from rejected or withdrawn edits once they're old enough."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, days, **options):
        cutoff = timezone.now() - dt.timedelta(days=days)
        edits = SuggestionEdit.objects.filter(
            status__in=[
                SuggestionEdit.Status.REJECTED,
                SuggestionEdit.Status.WITHDRAWN,
            ],
            resolved_at__lt=cutoff,
        ).exclude(explanation_audio="")
        count = 0
        for edit in edits:
            edit.explanation_audio.delete(save=False)
            edit.explanation_audio = ""
            edit.audio_duration_ms = None
            # Edits must keep an explanation, so leave a marker in place of the clip.
            edit.explanation = "(audio clip deleted)"
            edit.save(
                update_fields=["explanation_audio", "audio_duration_ms", "explanation"]
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} audio clip(s)."))
