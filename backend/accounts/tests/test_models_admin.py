import pytest
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_new_users_can_moderate_by_default():
    user = get_user_model().objects.create_user(username="alice")
    assert user.can_moderate is True
    assert user.apple_sub is None


def test_health(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.fixture
def admin_client_logged_in(client, django_user_model):
    admin = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="pw-for-tests"
    )
    client.force_login(admin)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "/admin/",
        "/admin/accounts/user/",
        "/admin/accounts/user/add/",
        "/admin/auth/group/",
    ],
)
def test_admin_pages_render(admin_client_logged_in, url):
    assert admin_client_logged_in.get(url).status_code == 200


@pytest.mark.django_db
def test_admin_can_create_user(admin_client_logged_in, django_user_model):
    response = admin_client_logged_in.post(
        "/admin/accounts/user/add/",
        {
            "username": "bob",
            "usable_password": "true",
            "password1": "a-long-test-password-123",
            "password2": "a-long-test-password-123",
        },
    )
    assert response.status_code == 302
    bob = django_user_model.objects.get(username="bob")
    assert bob.can_moderate is True

    change_page = admin_client_logged_in.get(f"/admin/accounts/user/{bob.pk}/change/")
    assert change_page.status_code == 200
    assert b"can_moderate" in change_page.content


@pytest.mark.django_db
def test_admin_can_ban_and_unban(admin_client_logged_in, django_user_model):
    bob = django_user_model.objects.create_user(username="bob")

    admin_client_logged_in.post(
        "/admin/accounts/user/",
        {"action": "ban_from_moderating", "_selected_action": [bob.pk]},
    )
    bob.refresh_from_db()
    assert bob.can_moderate is False

    admin_client_logged_in.post(
        "/admin/accounts/user/",
        {"action": "allow_moderating", "_selected_action": [bob.pk]},
    )
    bob.refresh_from_db()
    assert bob.can_moderate is True
