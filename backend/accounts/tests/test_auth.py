from unittest import mock

import pytest

from accounts import apple

pytestmark = pytest.mark.django_db


@pytest.fixture
def apple_token(monkeypatch):
    """Pretend Apple verified the identity token; the token text is the 'sub'."""

    def verify(token):
        if token == "bad":
            raise apple.AppleAuthError("Invalid Apple identity token")
        return {"sub": token, "aud": "com.example.films"}

    monkeypatch.setattr(apple, "verify_identity_token", verify)


def sign_in(client, sub="apple-user-1", **extra):
    return client.post(
        "/api/v1/auth/apple/",
        {"identity_token": sub, **extra},
        content_type="application/json",
    )


def test_first_sign_in_creates_account_without_a_name(client, apple_token):
    response = sign_in(client)

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["user"]["display_name"] == ""
    assert body["user"]["profile_complete"] is False
    assert "username" not in body["user"]
    assert body["access"] and body["refresh"]


def test_signing_in_again_returns_the_same_account(client, apple_token):
    first = sign_in(client).json()
    second = sign_in(client)

    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["user"] == first["user"]


def test_invalid_identity_token(client, apple_token):
    assert sign_in(client, "bad").status_code == 401


def test_disabled_account_cannot_sign_in(client, apple_token, django_user_model):
    sign_in(client)
    django_user_model.objects.update(is_active=False)
    assert sign_in(client).status_code == 403


def test_authorization_code_is_exchanged_for_revocable_token(
    client, apple_token, django_user_model, monkeypatch
):
    monkeypatch.setattr(
        apple, "exchange_authorization_code", lambda code: f"refresh-for-{code}"
    )
    sign_in(client, authorization_code="abc")
    assert django_user_model.objects.get().apple_refresh_token == "refresh-for-abc"


def test_access_token_authenticates_and_refresh_rotates(client, apple_token):
    tokens = sign_in(client).json()

    me = client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert me.status_code == 200
    assert me.json()["pending_edits"] == 0
    assert me.json()["max_pending_edits"] == 8

    refreshed = client.post(
        "/api/v1/auth/refresh/",
        {"refresh": tokens["refresh"]},
        content_type="application/json",
    )
    assert refreshed.status_code == 200
    # The old refresh token is blacklisted after rotation.
    reused = client.post(
        "/api/v1/auth/refresh/",
        {"refresh": tokens["refresh"]},
        content_type="application/json",
    )
    assert reused.status_code == 401


def test_me_requires_sign_in(client):
    assert client.get("/api/v1/me/").status_code == 401


@pytest.fixture
def user_client(token_client, django_user_model):
    return token_client(django_user_model.objects.create_user(username="first-handle"))


def test_choose_display_name(user_client):
    response = user_client.patch(
        "/api/v1/me/", {"display_name": "  Adam  "}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Adam"
    assert response.json()["profile_complete"] is True


@pytest.mark.parametrize("display_name", ["", "   ", "x" * 51])
def test_invalid_display_names(user_client, display_name):
    response = user_client.patch(
        "/api/v1/me/", {"display_name": display_name}, content_type="application/json"
    )
    assert response.status_code == 400


def test_display_names_need_not_be_unique(user_client, django_user_model):
    django_user_model.objects.create_user(username="other", display_name="Sam")
    response = user_client.patch(
        "/api/v1/me/", {"display_name": "Sam"}, content_type="application/json"
    )
    assert response.status_code == 200


def test_can_moderate_is_read_only(user_client):
    user_client.patch(
        "/api/v1/me/", {"can_moderate": False}, content_type="application/json"
    )
    user_client.user.refresh_from_db()
    assert user_client.user.can_moderate is True


def test_delete_account_revokes_apple_token(user_client, django_user_model):
    user_client.user.apple_refresh_token = "apple-refresh"
    user_client.user.save()

    with mock.patch.object(apple, "revoke_refresh_token") as revoke:
        response = user_client.delete("/api/v1/me/")

    assert response.status_code == 204
    revoke.assert_called_once_with("apple-refresh")
    assert not django_user_model.objects.exists()
