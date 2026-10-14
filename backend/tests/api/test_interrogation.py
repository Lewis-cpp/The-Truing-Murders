import json
import uuid

import pytest
from conftest import ORIGIN
from fastapi.testclient import TestClient
from player import CASE_VERSION, Player
from sqlalchemy import select, text

from backend.application.case import default_case_path
from backend.application.catalog import import_case
from backend.infrastructure.database.models import GameEventLog, NpcState

pytestmark = [pytest.mark.api, pytest.mark.integration]


def error_code(response) -> str:
    return response.json()["error"]["code"]


def outcome(response) -> dict:
    return response.json()["data"]["outcome"]


def interrogating(client) -> Player:
    player = Player(client)
    player.start()
    for action in ("A01", "A02", "A03"):
        player.investigate(action)
    player.talk()
    return player


def test_topic_records_testimony_once(client):
    player = interrogating(client)
    asked = player.ask_topic("Q01")
    assert asked.status_code == 201
    assert asked.json()["business_status"] == "COMMITTED"
    assert "B17的原件" in asked.json()["data"]["fixed_reply"]
    assert outcome(asked)["reason_code"] == "TESTIMONY_RECORDED"
    [testimony] = outcome(asked)["disclosed_information"]
    assert testimony["information_ref"] == {"kind": "KNOWLEDGE", "id": "K03"}
    assert testimony["credibility"] == "UNVERIFIED"
    assert testimony["source"] == {"kind": "NPC", "id": "NPC01", "label": "沈砚"}
    topics = outcome(asked)["npc"]["topics"]
    assert topics == [{"topic_id": "Q01", "label": "档案室丢了什么？", "asked": True}]
    again = player.ask_topic("Q01")
    assert again.json()["business_status"] == "NOOP"
    assert outcome(again)["reason_code"] == "TOPIC_ALREADY_ASKED"
    unknown = player.ask_topic("Q99")
    assert (unknown.status_code, error_code(unknown)) == (422, "INVALID_ACTION_REFERENCE")
    known = player.load()["known_information"]
    assert [k["information_ref"]["id"] for k in known] == ["K01", "K03"]


def test_contradiction_needs_recorded_testimony_and_moves_no_lie(client, db):
    player = interrogating(client)
    # Unasked, hidden, public and unknown entries get one answer, so nothing hidden leaks.
    refusals = [player.contradict(k, "E03") for k in ("K03", "K02", "K01", "K99")]
    assert {(r.status_code, error_code(r)) for r in refusals} == {(422, "INVALID_ACTION_REFERENCE")}
    assert len({r.json()["error"]["message"] for r in refusals}) == 1
    player.ask_topic("Q01")
    confirmed = player.contradict("K03", "E03")
    assert confirmed.json()["business_status"] == "COMMITTED"
    assert outcome(confirmed)["reason_code"] == "CONTRADICTION_CONFIRMED"
    assert outcome(confirmed)["summary"].startswith("矛盾成立：")
    assert "我是猜的" in confirmed.json()["data"]["fixed_reply"]
    assert outcome(confirmed)["npc"]["admission_progress"] == "NONE"
    repeat = player.contradict("K03", "E03")
    assert repeat.json()["business_status"] == "NOOP"
    assert outcome(repeat)["reason_code"] == "CONTRADICTION_ALREADY_POINTED"
    with db() as session:
        types = session.scalars(select(GameEventLog.event_type).order_by(GameEventLog.event_seq))
        state = session.scalar(select(NpcState))
        assert list(types)[-2:] == ["ASK_TOPIC", "POINT_CONTRADICTION"]
    assert (state.pressure, state.trust, state.lies_json["L01"]["stage"]) == (35, 40, "UNBROKEN")


def test_irrelevant_moves_lead_to_evasion_until_the_player_leaves(client, db):
    player = interrogating(client)
    player.ask_topic("Q01")
    wrong = player.contradict("K03", "E01")
    assert wrong.json()["business_status"] == "COMMITTED"
    assert outcome(wrong)["reason_code"] == "IRRELEVANT_MOVE"
    assert "戒备" in outcome(wrong)["summary"]
    assert outcome(wrong)["npc"]["is_evading"] is False
    evading = player.contradict("K03", "E02")
    evade_reply = evading.json()["data"]["fixed_reply"]
    assert outcome(evading)["reason_code"] == "NPC_EVADING"
    assert outcome(evading)["npc"]["is_evading"] is True
    assert outcome(evading)["npc"]["display_state"] == "EVADING"
    assert outcome(evading)["npc"]["fixed_statement"] == evade_reply
    for blocked in (
        player.present("E01"),
        player.ask_topic("Q01"),
        player.contradict("K03", "E03"),
        player.write("POST", player.path("/npcs/NPC01/conversations"), {"message": "说话"}),
    ):
        assert blocked.json()["business_status"] == "NOOP"
        assert blocked.json()["data"]["fixed_reply"] == evade_reply
    with db() as session:
        assert session.scalar(select(NpcState.irrelevant_streak)) == 2
    assert player.leave().status_code == 200
    with db() as session:
        assert session.scalar(select(NpcState.irrelevant_streak)) == 0
    assert player.talk().status_code == 201
    [npc] = player.load()["npcs"]
    assert (npc["is_evading"], npc["display_state"]) == (False, "CALM")
    assert outcome(player.present("E01"))["reason_code"] == "LIE_BROKEN"


def test_interrogation_responses_hide_numbers_and_unasked_testimony(client):
    player = interrogating(client)

    def hidden(responses, *markers):
        for response in responses:
            text_value = json.dumps(response, ensure_ascii=False)
            for marker in ("pressure", "trust", "irrelevant_streak", "我是猜的", *markers):
                assert marker not in text_value

    hidden(
        [player.load(), player.present("E02").json(), player.contradict("K03", "E03").json()],
        "B17的原件",
    )
    player.ask_topic("Q01")
    # A wrong pairing and the evasion it leads to describe the cost in words only.
    wrong, evading = player.contradict("K03", "E01"), player.contradict("K03", "E02")
    assert [outcome(r)["reason_code"] for r in (wrong, evading)] == [
        "IRRELEVANT_MOVE",
        "NPC_EVADING",
    ]
    hidden([wrong.json(), evading.json(), player.load()])


def test_unsupported_save_is_kept_and_can_be_replaced(client, db, tmp_path):
    player = Player(client)
    player.start()
    player.investigate("A01")
    old_id, old_version = player.session_id, player.version
    with db() as session, session.begin():
        session.execute(text("UPDATE case_template SET rule_execution_version = 'w1-slice-1'"))
    current = client.get("/api/v1/sessions/current")
    assert (current.status_code, error_code(current)) == (409, "SAVE_VERSION_UNSUPPORTED")
    assert current.json()["error"]["details"] == {
        "session_id": old_id,
        "state_version": old_version,
    }
    blocked = player.investigate("A02")
    assert (blocked.status_code, error_code(blocked)) == (409, "SAVE_VERSION_UNSUPPORTED")
    assert client.get("/api/v1/cases").json()["items"] == []

    raw = json.loads(default_case_path().read_text())
    raw["version"] = "test-copy"
    path = tmp_path / "case.json"
    path.write_text(json.dumps(raw, ensure_ascii=False))
    import_case(db, path)
    offered = client.get("/api/v1/cases").json()["items"]
    assert [c["case_version"] for c in offered] == ["test-copy"]
    body = {
        "case_id": "case_001",
        "case_version": "test-copy",
        "replaces_session_id": old_id,
        "confirm_restart": True,
    }
    restarted = player.write("POST", "/api/v1/sessions", body, version=old_version)
    assert restarted.status_code == 201
    assert restarted.json()["session_id"] != old_id
    old = client.get(f"/api/v1/sessions/{old_id}")
    assert error_code(old) == "SAVE_VERSION_UNSUPPORTED"

    with TestClient(client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as other:
        attempt = Player(other).write(
            "POST",
            "/api/v1/sessions",
            {"case_id": "case_001", "case_version": CASE_VERSION},
            version=None,
            key=uuid.uuid4(),
        )
        assert (attempt.status_code, error_code(attempt)) == (409, "CASE_UNAVAILABLE")
