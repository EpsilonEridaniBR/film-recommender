from django.conf import settings
from django.db.models import Count, OuterRef, Q, Subquery
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from films.models import Film
from films.importer import normalise_title
from films.queries import with_display_data
from films.serializers import FilmInfoSerializer, FilmSummarySerializer

from .models import EditVote, Suggestion, SuggestionEdit


def audio_url(field, request):
    if not field:
        return None
    url = field.url
    # Local disk storage gives relative URLs; Spaces gives absolute signed ones.
    return request.build_absolute_uri(url) if request and url.startswith("/") else url


class SuggestionSerializer(serializers.ModelSerializer):
    film = FilmSummarySerializer(source="suggested_film")
    audio_url = serializers.SerializerMethodField()
    recommended_by = serializers.SerializerMethodField()

    class Meta:
        model = Suggestion
        fields = [
            "id",
            "film",
            "explanation",
            "audio_url",
            "audio_duration_ms",
            "language",
            "recommended_by",
        ]

    def get_audio_url(self, suggestion) -> str | None:
        return audio_url(suggestion.explanation_audio, self.context.get("request"))

    def get_recommended_by(self, suggestion) -> str | None:
        """The recommender's display name; null for seeded suggestions or
        deleted accounts."""
        edit = suggestion.approved_edit
        user = edit.proposer if edit else None
        return (user.display_name or None) if user else None


class FilmDetailSerializer(FilmInfoSerializer):
    suggestions = serializers.SerializerMethodField()
    max_suggestions = serializers.SerializerMethodField()

    class Meta(FilmInfoSerializer.Meta):
        fields = FilmInfoSerializer.Meta.fields + ["suggestions", "max_suggestions"]

    def get_max_suggestions(self, film) -> int:
        """How many suggestions a film can have; more can be added below this."""
        return settings.SUGGESTIONS_PER_FILM

    @extend_schema_field(SuggestionSerializer(many=True))
    def get_suggestions(self, film):
        data = SuggestionSerializer(
            film.suggestions.all(), many=True, context=self.context
        ).data
        # Suggestions have no order of their own: alphabetical in the reader's language.
        return sorted(data, key=lambda s: normalise_title(s["film"]["title"]))


def edits_for_display(queryset, user=None):
    """Annotate vote tallies (and the user's own vote) and prefetch film data."""
    for prefix in ("source_film__", "proposed_film__", "replaced_film__"):
        queryset = with_display_data(queryset, prefix=prefix)
    queryset = queryset.select_related(
        "source_film", "proposed_film", "replaced_film", "proposer"
    ).annotate(
        approvals=Count("votes", filter=Q(votes__approve=True)),
        rejections=Count("votes", filter=Q(votes__approve=False)),
    )
    if user and user.is_authenticated:
        queryset = queryset.annotate(
            my_vote=Subquery(
                EditVote.objects.filter(edit=OuterRef("pk"), voter=user).values(
                    "approve"
                )[:1]
            )
        )
    return queryset


class EditSerializer(serializers.ModelSerializer):
    film = FilmSummarySerializer(source="source_film")
    proposed_film = FilmSummarySerializer(allow_null=True)
    replaced_film = FilmSummarySerializer(allow_null=True)
    proposer = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    approvals = serializers.IntegerField(read_only=True, default=0)
    rejections = serializers.IntegerField(read_only=True, default=0)
    my_vote = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = SuggestionEdit
        fields = [
            "id",
            "film",
            "action",
            "replaced_film",
            "proposed_film",
            "explanation",
            "audio_url",
            "audio_duration_ms",
            "language",
            "proposer",
            "status",
            "note",
            "created_at",
            "resolved_at",
            "approvals",
            "rejections",
            "my_vote",
            "is_mine",
        ]

    def get_proposer(self, edit) -> str | None:
        """The proposer's display name; null for seeded edits or deleted accounts."""
        return (edit.proposer.display_name or None) if edit.proposer else None

    def get_audio_url(self, edit) -> str | None:
        return audio_url(edit.explanation_audio, self.context.get("request"))

    def get_my_vote(self, edit) -> bool | None:
        """True = approved, False = rejected, null = hasn't voted."""
        return getattr(edit, "my_vote", None)

    def get_is_mine(self, edit) -> bool:
        """Whether the signed-in user proposed this edit (names aren't unique)."""
        request = self.context.get("request")
        user = request.user if request else None
        return bool(user and user.is_authenticated and edit.proposer_id == user.pk)


class FilmByTmdbIdField(serializers.IntegerField):
    def to_internal_value(self, data):
        tmdb_id = super().to_internal_value(data)
        try:
            return Film.objects.get(tmdb_id=tmdb_id)
        except Film.DoesNotExist:
            raise serializers.ValidationError("No film with that TMDB id.")


class EditCreateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=SuggestionEdit.Action.choices)
    proposed_film = FilmByTmdbIdField(
        required=False, help_text="TMDB id of the film to suggest (add/replace)."
    )
    replaced_film = FilmByTmdbIdField(
        required=False,
        help_text="TMDB id of the suggested film to take out (replace/remove).",
    )
    explanation = serializers.CharField(required=False, allow_blank=True)
    audio = serializers.FileField(
        required=False, help_text="A recorded explanation instead of text."
    )
    language = serializers.ChoiceField(choices=settings.LANGUAGES, required=False)

    def validate(self, data):
        action = data["action"]
        if action in ("add", "replace") and not data.get("proposed_film"):
            raise serializers.ValidationError(
                {"proposed_film": "Choose a film to suggest."}
            )
        if action in ("replace", "remove") and not data.get("replaced_film"):
            raise serializers.ValidationError(
                {"replaced_film": "Choose the suggestion to change."}
            )
        if action == "add":
            data.pop("replaced_film", None)
        if action == "remove":
            data.pop("proposed_film", None)
        return data


class VoteSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    comment = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ReportSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
