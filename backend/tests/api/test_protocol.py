import json
import uuid

import pytest
from conftest import ORIGIN
from fastapi.testclient import TestClient
from player import CORRECT, Player

pytestmark = [pytest.mark.api, pytest.mark.integration]


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_same_key_replays_and_different_input_conflicts(client):
    player = Player(client)
    player.start()
    key = uuid.uuid4()
    first = player.investigate("A01", key=key, version=1)
    again = player.investigate("A01", key=key, version=1)
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert len(player.load()["evidence"]) == 1
    assert player.load()["session"]["state_version"] == 2
    conflict = player.investigate("A02", key=key, version=1)
    assert conflict.status_code == 409
    assert error_code(conflict) == "IDEMPOTENCY_KEY_CONFLICT"
    record = client.get(f"/api/v1/requests/{key}").json()
    assert record["status"] == "COMMITTED"
    assert record["result"]["data"]["action_id"] == "A01"


def test_business_rejection_is_stored_and_atomic(client):
    player = Player(client)
    player.start()
    key = uuid.uuid4()
    rejected = player.investigate("A03", key=key)
    assert rejected.status_code == 409
    assert error_code(rejected) == "ACTION_UNAVAILABLE"
    assert player.investigate("A03", key=key).json()["error"]["code"] == "ACTION_UNAVAILABLE"
    record = client.get(f"/api/v1/requests/{key}").json()
    assert record["status"] == "REJECTED"
    assert record["original_http_status"] == 409
    assert record["error"]["code"] == "ACTION_UNAVAILABLE"
    view = player.load()
    assert view["session"]["state_version"] == 1
    assert view["evidence"] == []


def test_stale_version_and_phase_checks_change_nothing(client):
    player = Player(client)
    player.start()
    player.investigate("A01")
    stale = player.investigate("A02", version=1)
    assert stale.status_code == 409
    assert error_code(stale) == "STATE_VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["current_state_version"] == 2
    wrong_phase = player.present("E01")
    assert (wrong_phase.status_code, error_code(wrong_phase)) == (409, "ACTION_NOT_ALLOWED")
    assert player.load()["session"]["state_version"] == 2


def test_repeated_presentation_with_new_keys_adds_no_second_effect(client):
    player = Player(client)
    player.start()
    player.investigate("A01")
    player.talk()
    first = player.present("E01").json()
    second = player.present("E01").json()
    assert first["state_changed"] is True
    assert second["business_status"] == "NOOP"
    assert second["data"]["outcome"]["reason_code"] == "ALREADY_PRESENTED"
    assert second["result_state_version"] == first["result_state_version"]
    unheld = player.present("E03")
    assert (unheld.status_code, error_code(unheld)) == (422, "EVIDENCE_NOT_OWNED")


def test_chat_returns_fixed_statement_without_changing_state(client):
    player = Player(client)
    player.start()
    player.talk()
    response = player.write(
        "POST", player.path("/npcs/NPC01/conversations"), {"message": "停电时你在哪里？"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["business_status"] == "NOOP"
    assert body["data"]["fixed_reply"] == "停电时我一直在休息区，没有去过档案室。"
    other = player.write("POST", player.path("/npcs/NPC02/conversations"), {"message": "你好"})
    assert (other.status_code, error_code(other)) == (409, "NPC_UNAVAILABLE")


def test_other_visitors_and_anonymous_requests_cannot_reach_a_save(client):
    owner = Player(client)
    owner.start()
    key = uuid.uuid4()
    owner.investigate("A01", key=key)
    with TestClient(client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as other_client:
        assert other_client.get(owner.path("")).json()["error"]["code"] == "VISITOR_AUTH_REQUIRED"
        intruder = Player(other_client)
        intruder.session_id, intruder.version = owner.session_id, owner.version
        assert other_client.get(owner.path("")).status_code == 404
        attempt = intruder.investigate("A02")
        assert (attempt.status_code, error_code(attempt)) == (404, "SESSION_NOT_FOUND")
        assert other_client.get(f"/api/v1/requests/{key}").status_code == 404
        assert other_client.get("/api/v1/sessions/current").json()["session"] is None
    assert owner.load()["session"]["state_version"] == 2


@pytest.mark.parametrize("origin", [None, "https://evil.example"])
def test_writes_require_an_allowed_origin(client, origin):
    player = Player(client)
    player.start()
    headers = {"Idempotency-Key": str(uuid.uuid4()), "X-Expected-State-Version": "1"}
    client.headers.pop("Origin")
    if origin:
        headers["Origin"] = origin
    response = client.post(
        player.path("/scenes/S01/investigations"), json={"action_id": "A01"}, headers=headers
    )
    assert (response.status_code, error_code(response)) == (403, "ORIGIN_NOT_ALLOWED")
    client.headers["Origin"] = ORIGIN
    assert player.load()["evidence"] == []


def test_header_and_body_protocol_errors(client):
    player = Player(client)
    player.start()
    path = player.path("/scenes/S01/investigations")
    no_key = client.post(path, json={"action_id": "A01"}, headers={"X-Expected-State-Version": "1"})
    assert (no_key.status_code, error_code(no_key)) == (400, "IDEMPOTENCY_KEY_REQUIRED")
    bad_key = client.post(path, json={"action_id": "A01"}, headers={"Idempotency-Key": "x"})
    assert error_code(bad_key) == "INVALID_IDEMPOTENCY_KEY"
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    missing_version = client.post(path, json={"action_id": "A01"}, headers=headers)
    assert (missing_version.status_code, error_code(missing_version)) == (
        428,
        "STATE_VERSION_REQUIRED",
    )
    headers["X-Expected-State-Version"] = "1"
    extra = client.post(path, json={"action_id": "A01", "pressure": 100}, headers=headers)
    assert (extra.status_code, error_code(extra)) == (422, "VALIDATION_ERROR")
    raw = {**headers, "Content-Type": "application/json"}
    malformed = client.post(path, content=b"{", headers=raw)
    assert (malformed.status_code, error_code(malformed)) == (400, "MALFORMED_JSON")
    text_body = client.post(path, content=b"A01", headers={**headers, "Content-Type": "text/plain"})
    assert (text_body.status_code, error_code(text_body)) == (415, "UNSUPPORTED_MEDIA_TYPE")
    huge = json.dumps({"action_id": "A" * 70000}).encode()
    too_large = client.post(path, content=huge, headers=raw)
    assert (too_large.status_code, error_code(too_large)) == (413, "PAYLOAD_TOO_LARGE")
    assert too_large.headers["cache-control"] == "no-store"
    assert too_large.json()["error"]["trace_id"] == too_large.headers["x-trace-id"]
    assert player.load()["session"]["state_version"] == 1


def test_reads_have_no_side_effects(client):
    player = Player(client)
    player.start()
    player.investigate("A01")
    before = player.load()
    for path in ("", "/accusation", "/review"):
        client.get(player.path(path))
    client.get("/api/v1/sessions/current")
    client.get("/api/v1/cases")
    assert player.load() == before


def test_initial_and_rejected_responses_hide_secrets(client):
    player = Player(client)
    created = json.dumps(player.start().json(), ensure_ascii=False)
    rejected = json.dumps(player.investigate("A03").json(), ensure_ascii=False)
    review = json.dumps(client.get(player.path("/review")).json(), ensure_ascii=False)
    for text in (created, rejected, review):
        for marker in (
            "我承认21:10",  # admitted statement
            "沈砚承认21:10",  # private knowledge
            "利用工程检修",  # truth explanation
            "admission_pressure_min",
            "pressure",
            "B17实验原始记录",  # unheld evidence content
        ):
            assert marker not in text


def test_restart_creates_an_independent_game_and_freezes_the_old_entry(client):
    player = Player(client)
    player.start()
    player.investigate("A01")
    old_id, old_version = player.session_id, player.version
    body = {"case_id": "case_001", "case_version": "1-slice"}
    exists = player.write("POST", "/api/v1/sessions", body, version=None)
    assert (exists.status_code, error_code(exists)) == (409, "CURRENT_SESSION_EXISTS")
    restart = {**body, "replaces_session_id": old_id}
    unconfirmed = player.write("POST", "/api/v1/sessions", restart, version=old_version)
    assert error_code(unconfirmed) == "CONFIRMATION_REQUIRED"
    restart["confirm_restart"] = True
    stale = player.write("POST", "/api/v1/sessions", restart, version=1)
    assert error_code(stale) == "STATE_VERSION_CONFLICT"
    new = player.write("POST", "/api/v1/sessions", restart, version=old_version)
    assert new.status_code == 201
    assert new.json()["data"]["evidence"] == []
    assert new.json()["session_id"] != old_id
    old = client.get(f"/api/v1/sessions/{old_id}").json()
    assert old["session"]["is_current"] is False
    assert old["session"]["available_actions"] == []
    assert [e["evidence_id"] for e in old["evidence"]] == ["E01"]
    player.session_id, player.version = old_id, old_version
    late = player.investigate("A02")
    assert (late.status_code, error_code(late)) == (409, "SESSION_NOT_CURRENT")


def test_accusation_is_final_and_reviews_wait_for_closure(client):
    player = Player(client)
    player.start()
    assert error_code(client.get(player.path("/review"))) == "REVIEW_NOT_AVAILABLE"
    player.accuse()
    unconfirmed = player.submit(confirm=False)
    assert (unconfirmed.status_code, error_code(unconfirmed)) == (422, "CONFIRMATION_REQUIRED")
    unheld = player.submit()
    assert (unheld.status_code, error_code(unheld)) == (422, "EVIDENCE_NOT_OWNED")
    guess = {**CORRECT, "cited_evidence_ids": [], "step_evidence_links": []}
    key = uuid.uuid4()
    first = player.submit(guess, key=key)
    assert first.status_code == 201
    assert first.json()["data"]["verdict"]["category"] == "PARTIALLY_CORRECT"
    assert first.json()["data"]["verdict"]["score"] == "75.00"
    assert first.headers["location"] == player.path("/accusation")
    replay = player.submit(guess, key=key, version=first.json()["state_version_before"])
    assert replay.json() == first.json()
    again = player.submit(guess)
    assert (again.status_code, error_code(again)) == (409, "ACCUSATION_ALREADY_SUBMITTED")
    assert client.get(player.path("/accusation")).json()["data"] == first.json()["data"]
    review = client.get(player.path("/review")).json()["data"]
    assert {e["evidence_id"] for e in review["missed_evidence"]} == {"E01", "E02", "E03"}
    assert player.load()["evidence"] == []


def test_wrong_but_legal_accusation_closes_the_game(client):
    player = Player(client)
    player.start()
    player.accuse()
    wrong = {**CORRECT, "suspect_character_id": "NPC02", "cited_evidence_ids": []}
    wrong["step_evidence_links"] = []
    response = player.submit(wrong)
    assert response.status_code == 201
    assert response.json()["data"]["verdict"]["category"] == "INCORRECT"
    assert response.json()["phase_after"] == "REVIEW"
