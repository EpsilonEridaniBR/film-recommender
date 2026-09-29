import pytest

from films import importer
from films.models import Film
from films.tests.factories import parsed


@pytest.fixture
def films(db):
    """A small catalogue, keyed by English title."""
    importer.upsert_movies(
        [
            parsed(289, "Casablanca"),
            parsed(329865, "Arrival", translations=[("fr", "FR", "Premier Contact")]),
            parsed(14160, "Up", translations=[("fr", "FR", "Là-haut")]),
            parsed(8363, "Zodiac"),
            parsed(603, "The Matrix"),
        ]
    )
    return {str(f): f for f in Film.objects.all()} | {
        f.safe_translation_getter("title"): f for f in Film.objects.all()
    }


@pytest.fixture
def users(django_user_model):
    return {
        name: django_user_model.objects.create_user(
            username=name, display_name=name.title()
        )
        for name in ["alice", "bob", "carol", "dave"]
    }


@pytest.fixture
def media(settings, tmp_path):
    """Store uploads in a temporary folder on local disk."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_URL = "/media/"
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
    return settings.MEDIA_ROOT


def make_clip(tmp_path, seconds, name="clip.wav"):
    """A real audio file (a sine tone) generated with ffmpeg."""
    import subprocess

    from django.core.files.uploadedfile import SimpleUploadedFile

    path = tmp_path / name
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            str(path),
        ],
        check=True,
    )
    return SimpleUploadedFile(name, path.read_bytes(), content_type="audio/wav")


@pytest.fixture
def clip(tmp_path):
    return lambda seconds=2, name="clip.wav": make_clip(tmp_path, seconds, name)
