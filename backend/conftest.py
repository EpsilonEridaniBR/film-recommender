import pytest


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    # The production manifest storage needs collectstatic to have run first.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def token_client(client):
    """Returns a function that makes the test client call the API as a user."""
    from rest_framework_simplejwt.tokens import RefreshToken

    def as_user(user):
        token = RefreshToken.for_user(user).access_token
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        client.user = user
        return client

    return as_user


@pytest.fixture(autouse=True)
def _reset_language():
    # Requests with Accept-Language leave that language active on the thread.
    from django.utils import translation

    translation.activate("en")
    yield
    translation.activate("en")
