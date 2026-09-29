import pytest

from films import importer
from films.models import Film, Genre
from films.tests.factories import parsed

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(
        django_user_model.objects.create_superuser(username="admin", password="pw")
    )
    return client


def test_catalogue_admin_pages_render(admin_client):
    importer.upsert_movies([parsed(329865, "Arrival")])
    film = Film.objects.get()
    Genre.objects.create(tmdb_id=18, name="Drama")

    for url in [
        "/admin/films/film/",
        "/admin/films/film/?q=arrival",
        f"/admin/films/film/{film.pk}/change/",
        "/admin/films/genre/",
        "/admin/films/person/",
        "/admin/films/skippedtmdbfilm/",
    ]:
        assert admin_client.get(url).status_code == 200, url
