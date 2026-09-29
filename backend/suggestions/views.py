from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import translation
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsModerator
from films.models import Film

from . import services
from .models import Report, Suggestion, SuggestionEdit
from .serializers import (
    EditCreateSerializer,
    EditSerializer,
    ReportSerializer,
    VoteSerializer,
    edits_for_display,
)

Status = SuggestionEdit.Status


class InvalidEdit(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_edit"


def edit_response(request, edit, status_code=status.HTTP_200_OK):
    edit = edits_for_display(SuggestionEdit.objects.all(), request.user).get(pk=edit.pk)
    return Response(
        EditSerializer(edit, context={"request": request}).data, status=status_code
    )


class FilmEditCreateView(APIView):
    """Propose adding, replacing or removing one of a film's suggestions.
    Send multipart form data to include an audio clip."""

    permission_classes = [IsModerator]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "edits"

    @extend_schema(request=EditCreateSerializer, responses={201: EditSerializer})
    def post(self, request, tmdb_id):
        film = get_object_or_404(Film, tmdb_id=tmdb_id)
        data = EditCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        fields = data.validated_data
        try:
            edit = services.submit_edit(
                request.user,
                film,
                fields["action"],
                proposed_film=fields.get("proposed_film"),
                replaced_film=fields.get("replaced_film"),
                explanation=fields.get("explanation", ""),
                audio=fields.get("audio"),
                language=fields.get("language") or translation.get_language()[:2],
            )
        except services.EditError as exc:
            raise InvalidEdit(str(exc))
        return edit_response(request, edit, status.HTTP_201_CREATED)


class FilmHistoryView(generics.ListAPIView):
    """Approved changes to a film's suggestions, newest first."""

    serializer_class = EditSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        film = get_object_or_404(Film, tmdb_id=self.kwargs["tmdb_id"])
        return edits_for_display(
            SuggestionEdit.objects.filter(
                source_film=film, status__in=[Status.APPROVED, Status.AUTO_APPROVED]
            ),
            self.request.user,
        ).order_by("-resolved_at")


class EditListView(generics.ListAPIView):
    """The review queue (pending edits, oldest first) or other edits by status."""

    serializer_class = EditSerializer
    permission_classes = [IsModerator]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status", str, enum=Status.values, description="Default: pending"
            ),
            OpenApiParameter("film", int, description="Only edits on this TMDB id"),
            OpenApiParameter(
                "needs_my_vote",
                bool,
                description="Only edits you didn't propose and haven't voted on",
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        params = self.request.query_params
        edit_status = params.get("status", Status.PENDING)
        queryset = SuggestionEdit.objects.filter(status=edit_status)
        if params.get("film"):
            queryset = queryset.filter(source_film__tmdb_id=params["film"])
        if params.get("needs_my_vote") in ("1", "true"):
            user = self.request.user
            queryset = queryset.exclude(
                Q(proposer=user) | Q(votes__voter=user)
            ).distinct()
        ordering = "created_at" if edit_status == Status.PENDING else "-resolved_at"
        return edits_for_display(queryset, self.request.user).order_by(ordering)


class MyEditsView(generics.ListAPIView):
    """Your own edits, newest first."""

    serializer_class = EditSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return edits_for_display(
            SuggestionEdit.objects.filter(proposer=self.request.user),
            self.request.user,
        ).order_by("-created_at")


class EditDetailView(APIView):
    permission_classes = [IsModerator]

    @extend_schema(responses=EditSerializer)
    def get(self, request, pk):
        edit = get_object_or_404(SuggestionEdit, pk=pk)
        return edit_response(request, edit)

    @extend_schema(responses=EditSerializer, description="Withdraw your pending edit.")
    def delete(self, request, pk):
        get_object_or_404(SuggestionEdit, pk=pk)
        try:
            edit = services.withdraw(request.user, pk)
        except services.EditError as exc:
            raise InvalidEdit(str(exc))
        return edit_response(request, edit)


class EditVoteView(APIView):
    """Approve or reject a pending edit. Voting again changes your vote."""

    permission_classes = [IsModerator]

    @extend_schema(request=VoteSerializer, responses=EditSerializer)
    def post(self, request, pk):
        get_object_or_404(SuggestionEdit, pk=pk)
        data = VoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            edit = services.vote(
                request.user,
                pk,
                data.validated_data["approve"],
                data.validated_data.get("comment", ""),
            )
        except services.EditError as exc:
            raise InvalidEdit(str(exc))
        return edit_response(request, edit)


class ReportSuggestionView(APIView):
    """Flag a suggestion as inappropriate for an admin to review."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ReportSerializer, responses={201: None})
    def post(self, request, pk):
        suggestion = get_object_or_404(Suggestion, pk=pk)
        data = ReportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        Report.objects.update_or_create(
            suggestion=suggestion,
            reporter=request.user,
            defaults={
                "reason": data.validated_data.get("reason", ""),
                "resolved": False,
            },
        )
        return Response(status=status.HTTP_201_CREATED)
