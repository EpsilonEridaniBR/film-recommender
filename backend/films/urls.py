from django.urls import path

from . import views

urlpatterns = [
    path("films/search/", views.FilmSearchView.as_view(), name="film-search"),
    path("films/<int:tmdb_id>/", views.FilmDetailView.as_view(), name="film-detail"),
]
