from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import translation
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.throttling import ScopedRateThrottle

from suggestions.models import Suggestion
from suggestions.serializers import FilmDetailSerializer

from .models import Film
from .queries import with_display_data
from .search import search_films
from .serializers import FilmSearchResultSerializer


class FilmSearchView(generics.ListAPIView):
    serializer_class = FilmSearchResultSerializer
    pagination_class = None
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="Title to search for")]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Film.objects.none()
        return with_display_data(search_films(query, translation.get_language()[:2]))


class FilmDetailView(generics.RetrieveAPIView):
    serializer_class = FilmDetailSerializer
    lookup_field = "tmdb_id"

    def get_object(self):
        suggestions = with_display_data(
            Suggestion.objects.select_related(
                "suggested_film", "approved_edit__proposer"
            ),
            prefix="suggested_film__",
        )
        films = with_display_data(Film.objects.all()).prefetch_related(
            Prefetch("suggestions", queryset=suggestions)
        )
        return get_object_or_404(films, tmdb_id=self.kwargs["tmdb_id"])
