import pytest

from suggestions import seeding
from suggestions.models import Suggestion, SuggestionEdit


@pytest.fixture
def admin_client(client, django_user_model):
    admin = django_user_model.objects.create_superuser(username="admin", password="pw")
    client.force_login(admin)
    client.user = admin
    return client


def test_admin_pages_render(admin_client, films):
    seeding.create_seed_suggestion(
        films["Casablanca"].pk, films["Arrival"].pk, "Reason"
    )
    edit = SuggestionEdit.objects.get()
    suggestion = Suggestion.objects.get()

    for url in [
        "/admin/suggestions/suggestion/",
        "/admin/suggestions/suggestion/?q=casablanca",
        "/admin/suggestions/suggestion/add/",
        f"/admin/suggestions/suggestion/{suggestion.pk}/change/",
        "/admin/suggestions/suggestionedit/",
        f"/admin/suggestions/suggestionedit/{edit.pk}/change/",
    ]:
        assert admin_client.get(url).status_code == 200, url


def test_adding_in_admin_records_an_edit(admin_client, films):
    response = admin_client.post(
        "/admin/suggestions/suggestion/add/",
        {
            "source_film": films["Casablanca"].pk,
            "suggested_film": films["Arrival"].pk,
            "explanation": "Added by hand",
            "language": "en",
        },
    )

    assert response.status_code == 302
    edit = SuggestionEdit.objects.get()
    assert edit.proposer == admin_client.user
    assert edit.status == SuggestionEdit.Status.AUTO_APPROVED
    assert Suggestion.objects.get().approved_edit == edit


def test_admin_add_shows_errors_for_invalid_suggestions(admin_client, films, settings):
    settings.SUGGESTIONS_PER_FILM = 1
    seeding.create_seed_suggestion(
        films["Casablanca"].pk, films["Arrival"].pk, "Reason"
    )

    response = admin_client.post(
        "/admin/suggestions/suggestion/add/",
        {
            "source_film": films["Casablanca"].pk,
            "suggested_film": films["Up"].pk,
            "explanation": "One too many",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert b"maximum number of suggestions" in response.content
    assert Suggestion.objects.count() == 1


def test_admin_can_approve_pending_edits(admin_client, films, users):
    from suggestions import services

    seeding.create_seed_suggestion(films["Casablanca"].pk, films["Arrival"].pk, "x")
    edit = services.submit_edit(
        users["alice"],
        films["Casablanca"],
        SuggestionEdit.Action.REPLACE,
        proposed_film=films["Up"],
        replaced_film=films["Arrival"],
        explanation="Better",
    )

    response = admin_client.post(
        "/admin/suggestions/suggestionedit/",
        {"action": "approve_edits", "_selected_action": [edit.pk]},
    )

    assert response.status_code == 302
    edit.refresh_from_db()
    assert edit.status == SuggestionEdit.Status.APPROVED
    assert Suggestion.objects.get().suggested_film == films["Up"]


def test_removing_reported_suggestions_records_an_edit(admin_client, films, users):
    from suggestions.models import Report

    seeding.create_seed_suggestion(films["Casablanca"].pk, films["Arrival"].pk, "x")
    report = Report.objects.create(
        suggestion=Suggestion.objects.get(), reporter=users["alice"], reason="Rude"
    )
    assert admin_client.get("/admin/suggestions/report/").status_code == 200
    assert (
        admin_client.get(f"/admin/suggestions/report/{report.pk}/change/").status_code
        == 200
    )

    admin_client.post(
        "/admin/suggestions/report/",
        {"action": "remove_suggestions", "_selected_action": [report.pk]},
    )

    assert not Suggestion.objects.exists()
    removal = SuggestionEdit.objects.get(action=SuggestionEdit.Action.REMOVE)
    assert removal.status == SuggestionEdit.Status.APPROVED
    assert removal.proposer == admin_client.user
