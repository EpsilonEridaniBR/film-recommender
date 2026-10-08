import pytest

from suggestions import services
from suggestions.models import Report, Suggestion, SuggestionEdit

Action = SuggestionEdit.Action


@pytest.fixture
def as_user(token_client, users):
    return lambda name: token_client(users[name])


@pytest.fixture
def casablanca_with_arrival(films):
    services.apply_edit(
        SuggestionEdit.objects.create(
            source_film=films["Casablanca"],
            action=Action.ADD,
            proposed_film=films["Arrival"],
            explanation="seed",
        )
    )


def post_edit(client, tmdb_id=289, **data):
    return client.post(
        f"/api/v1/films/{tmdb_id}/edits/", data, content_type="application/json"
    )


def propose_replace(client):
    return post_edit(
        client,
        action="replace",
        replaced_film=329865,
        proposed_film=14160,
        explanation="Up is warmer",
    )


def test_propose_edits_requires_sign_in(client, films):
    response = post_edit(client, action="add", proposed_film=329865, explanation="x")
    assert response.status_code == 401


def test_add_via_api(as_user, films):
    response = post_edit(
        as_user("alice"), action="add", proposed_film=329865, explanation="Why not"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "auto_approved"
    assert body["proposer"] == "Alice"
    assert body["proposed_film"]["title"] == "Arrival"
    assert body["film"]["tmdb_id"] == 289


def test_add_with_audio_via_multipart(as_user, films, clip, media):
    response = as_user("alice").post(
        "/api/v1/films/289/edits/",
        {"action": "add", "proposed_film": 329865, "audio": clip()},
    )

    assert response.status_code == 201
    assert response.json()["audio_url"].startswith("http://testserver/media/audio/")
    detail = as_user("alice").get("/api/v1/films/289/").json()
    assert detail["suggestions"][0]["audio_url"].endswith(".m4a")


@pytest.mark.parametrize(
    "data, field",
    [
        ({"action": "add", "explanation": "x"}, "proposed_film"),
        ({"action": "remove"}, "replaced_film"),
        ({"action": "add", "proposed_film": 999, "explanation": "x"}, "proposed_film"),
    ],
)
def test_edit_validation_errors(as_user, films, data, field):
    response = post_edit(as_user("alice"), **data)
    assert response.status_code == 400
    assert field in response.json()


def test_rule_violations_return_400_with_detail(as_user, casablanca_with_arrival):
    response = post_edit(
        as_user("alice"), action="add", proposed_film=329865, explanation="dupe"
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "That film is already suggested."


def test_explanation_language_defaults_to_request_language(as_user, films):
    response = as_user("alice").post(
        "/api/v1/films/289/edits/",
        {"action": "add", "proposed_film": 329865, "explanation": "Parce que"},
        content_type="application/json",
        HTTP_ACCEPT_LANGUAGE="fr",
    )
    assert response.json()["language"] == "fr"


def test_queue_vote_and_history(as_user, casablanca_with_arrival):
    edit_id = propose_replace(as_user("alice")).json()["id"]

    queue = as_user("bob").get("/api/v1/edits/").json()
    assert [e["id"] for e in queue["results"]] == [edit_id]
    assert queue["results"][0]["my_vote"] is None
    assert queue["results"][0]["is_mine"] is False
    own_queue = as_user("alice").get("/api/v1/edits/").json()
    assert own_queue["results"][0]["is_mine"] is True

    first = (
        as_user("bob")
        .post(
            f"/api/v1/edits/{edit_id}/vote/",
            {"approve": True, "comment": "Agreed"},
            content_type="application/json",
        )
        .json()
    )
    assert (first["approvals"], first["my_vote"], first["status"]) == (
        1,
        True,
        "pending",
    )

    second = (
        as_user("carol")
        .post(
            f"/api/v1/edits/{edit_id}/vote/",
            {"approve": True},
            content_type="application/json",
        )
        .json()
    )
    assert second["status"] == "approved"

    detail = as_user("bob").get("/api/v1/films/289/").json()
    assert [s["film"]["title"] for s in detail["suggestions"]] == ["Up"]

    history = as_user("bob").get("/api/v1/films/289/history/").json()["results"]
    assert [h["action"] for h in history] == ["replace", "add"]


def test_needs_my_vote_filter(as_user, casablanca_with_arrival):
    edit_id = propose_replace(as_user("alice")).json()["id"]

    def queue(name):
        response = as_user(name).get("/api/v1/edits/", {"needs_my_vote": "true"})
        return [e["id"] for e in response.json()["results"]]

    assert queue("alice") == []  # own edit
    assert queue("bob") == [edit_id]
    as_user("bob").post(
        f"/api/v1/edits/{edit_id}/vote/",
        {"approve": False},
        content_type="application/json",
    )
    assert queue("bob") == []


def test_cannot_vote_on_own_edit(as_user, casablanca_with_arrival):
    edit_id = propose_replace(as_user("alice")).json()["id"]
    response = as_user("alice").post(
        f"/api/v1/edits/{edit_id}/vote/",
        {"approve": True},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_withdraw_and_my_edits(as_user, casablanca_with_arrival):
    edit_id = propose_replace(as_user("alice")).json()["id"]
    assert as_user("alice").get("/api/v1/me/").json()["pending_edits"] == 1

    assert as_user("bob").delete(f"/api/v1/edits/{edit_id}/").status_code == 400
    response = as_user("alice").delete(f"/api/v1/edits/{edit_id}/")
    assert response.json()["status"] == "withdrawn"

    mine = as_user("alice").get("/api/v1/me/edits/").json()["results"]
    assert [e["status"] for e in mine] == ["withdrawn"]
    assert as_user("alice").get("/api/v1/me/").json()["pending_edits"] == 0


def test_banned_users_cannot_use_the_queue(as_user, users, casablanca_with_arrival):
    users["bob"].can_moderate = False
    users["bob"].save()
    assert as_user("bob").get("/api/v1/edits/").status_code == 403
    assert propose_replace(as_user("bob")).status_code == 403


def test_history_is_public_and_hides_nothing_sensitive(client, casablanca_with_arrival):
    history = client.get("/api/v1/films/289/history/").json()["results"]
    assert history[0]["proposer"] is None  # seeded
    assert "my_vote" in history[0]


def test_report_a_suggestion(as_user, casablanca_with_arrival, client):
    suggestion_id = Suggestion.objects.get().pk

    assert (
        client.post(f"/api/v1/suggestions/{suggestion_id}/report/").status_code == 401
    )
    for _ in range(2):  # reporting twice just updates the report
        response = as_user("alice").post(
            f"/api/v1/suggestions/{suggestion_id}/report/",
            {"reason": "Spoilers"},
            content_type="application/json",
        )
        assert response.status_code == 201
    assert Report.objects.get().reason == "Spoilers"


def test_deleted_accounts_keep_their_edits_anonymously(as_user, users, films):
    post_edit(as_user("alice"), action="add", proposed_film=329865, explanation="x")
    as_user("alice").delete("/api/v1/me/")

    edit = SuggestionEdit.objects.get()
    assert edit.proposer is None
    assert Suggestion.objects.exists()


def test_users_without_a_display_name_cannot_moderate(
    token_client, django_user_model, casablanca_with_arrival
):
    client = token_client(django_user_model.objects.create_user(username="new"))

    assert client.get("/api/v1/edits/").status_code == 403
    assert propose_replace(client).status_code == 403

    client.patch(
        "/api/v1/me/", {"display_name": "Newbie"}, content_type="application/json"
    )
    assert propose_replace(client).status_code == 201


def test_suggestions_show_the_recommenders_display_name(as_user, films):
    post_edit(as_user("alice"), action="add", proposed_film=329865, explanation="x")

    suggestion = as_user("bob").get("/api/v1/films/289/").json()["suggestions"][0]

    assert suggestion["recommended_by"] == "Alice"


def test_seeded_suggestions_have_no_recommender(client, casablanca_with_arrival):
    suggestion = client.get("/api/v1/films/289/").json()["suggestions"][0]
    assert suggestion["recommended_by"] is None
