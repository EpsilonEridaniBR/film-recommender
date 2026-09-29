from django.urls import path

from . import views

urlpatterns = [
    path(
        "films/<int:tmdb_id>/edits/",
        views.FilmEditCreateView.as_view(),
        name="film-edit-create",
    ),
    path(
        "films/<int:tmdb_id>/history/",
        views.FilmHistoryView.as_view(),
        name="film-history",
    ),
    path("edits/", views.EditListView.as_view(), name="edit-list"),
    path("edits/<int:pk>/", views.EditDetailView.as_view(), name="edit-detail"),
    path("edits/<int:pk>/vote/", views.EditVoteView.as_view(), name="edit-vote"),
    path("me/edits/", views.MyEditsView.as_view(), name="my-edits"),
    path(
        "suggestions/<int:pk>/report/",
        views.ReportSuggestionView.as_view(),
        name="suggestion-report",
    ),
]
