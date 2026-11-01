"""v0.3 acceptance: the full case through HTTP and PostgreSQL, fixed replies only."""

import json
from pathlib import Path

import pytest
from conftest import make_client
from player import CORRECT, NO_CONFESSION_ORDER, Player, content_from

pytestmark = [pytest.mark.api, pytest.mark.integration]

EXPECTED = Path(__file__).resolve().parents[1] / "data/expected"
PATHS = json.loads((EXPECTED / "full_case_paths.json").read_text(encoding="utf-8"))
VERDICTS = json.loads((EXPECTED / "full_case_verdicts.json").read_text(encoding="utf-8"))
PUBLIC_CODE = {"EVASION_STARTED": "NPC_EVADING"}


def code(response) -> str:
    return response.json()["error"]["code"]


def test_no_confession_path_scores_full_marks(client):
    player = Player(client)
    created = player.start().json()
    assert created["result_state_version"] == 1
    assert [s["scene_id"] for s in created["data"]["scenes"]] == ["S01"]
    for index, action in enumerate(NO_CONFESSION_ORDER, start=2):
        response = player.investigate(action)
        assert response.status_code == 201, response.text
        assert response.json()["result_state_version"] == index
    view = player.load()
    assert view["session"]["phase"] == "DEEP_INVESTIGATION"
    assert len(view["evidence"]) == 12
    assert [s["scene_id"] for s in view["scenes"]] == ["S01", "S02", "S03", "S04"]
    assert {n["admission_progress"] for n in view["npcs"]} == {"NONE"}

    assert player.accuse().status_code == 201
    closed = player.submit()
    assert closed.status_code == 201, closed.text
    verdict = closed.json()["data"]["verdict"]
    assert (verdict["category"], verdict["score"], verdict["max_score"]) == (
        "CORRECT",
        "100.00",
        "100.00",
    )
    assert verdict["fixed_explanation"]
    assert all(c["matched"] and c["missing_evidence_ids"] == [] for c in verdict["criteria"])
    review = player.get("/review").json()["data"]
    assert review["missed_evidence"] == []
    assert len(review["evidence_chain"]) == 12
    assert "21:12" in review["truth"]["explanation"]


def test_unlocked_scenes_and_projection_flags_in_outcomes(client):
    player = Player(client)
    player.start()
    first = player.investigate("A01").json()["data"]["outcome"]
    assert [s["scene_id"] for s in first["unlocked_scenes"]] == ["S02", "S04"]
    assert first["timeline_changed"] is True  # T06 becomes visible
    assert first["relationships_changed"] is False
    second = player.investigate("A02").json()["data"]["outcome"]
    assert second["unlocked_scenes"] == []
    assert second["timeline_changed"] is False
    third = player.investigate("A03").json()
    assert [s["scene_id"] for s in third["data"]["outcome"]["unlocked_scenes"]] == ["S03"]
    assert third["data"]["outcome"]["relationships_changed"] is True  # R05
    assert third["phase_after"] == "DEEP_INVESTIGATION"
    fourth = player.investigate("A04").json()["data"]["outcome"]
    assert (fourth["relationships_changed"], fourth["timeline_changed"]) == (False, False)


def run_path(player, steps):
    for step in steps:
        op, expect = step["op"], step["expect"]
        if op == "talk":
            response = player.talk(step["npc"])
        elif op == "back":
            response = player.leave()
        elif op == "present":
            response = player.present(step["evidence"])
        elif op == "topic":
            response = player.ask_topic(step["topic"])
        else:
            response = player.contradict(step["knowledge"], step["evidence"])
        if "error" in expect:
            assert code(response) == expect["error"], step
            continue
        assert response.status_code in (200, 201), (step, response.text)
        body = response.json()
        if "outcome" in expect:
            want = PUBLIC_CODE.get(expect["outcome"], expect["outcome"])
            assert body["data"]["outcome"]["reason_code"] == want, step
        if "disclosed_add" in expect:
            got = [
                i["information_ref"]["id"] for i in body["data"]["outcome"]["disclosed_information"]
            ]
            assert sorted(got) == sorted(expect["disclosed_add"]), step
        if "phase" in expect:
            assert body["phase_after"] == expect["phase"], step
        speaker = player.active_npc or step.get("npc")
        if "display_state" in expect:
            assert player.npc(speaker)["display_state"] == expect["display_state"], step
        if "statement" in expect:
            assert player.npc(speaker)["fixed_statement"] == expect["statement"], step


@pytest.mark.parametrize(
    "name", ["full_confession", "reverse_layers_with_evasion", "testimony_and_contradictions"]
)
def test_hand_written_paths_over_http(client, name):
    player = Player(client)
    player.start()
    player.investigate_all()
    run_path(player, PATHS[name])


def test_confessions_do_not_change_the_verdict(client):
    player = Player(client)
    player.start()
    player.investigate_all()
    run_path(player, PATHS["full_confession"])
    assert player.accuse().status_code == 201
    verdict = player.submit().json()["data"]["verdict"]
    assert (verdict["category"], verdict["score"]) == ("CORRECT", "100.00")


@pytest.mark.parametrize("example", VERDICTS, ids=lambda e: e["name"])
def test_hand_written_verdicts_over_http(client, example):
    player = Player(client)
    player.start()
    player.investigate_all(example["actions"])
    assert player.accuse().status_code == 201
    closed = player.submit(content_from(example["accusation"]))
    assert closed.status_code == 201, closed.text
    verdict = closed.json()["data"]["verdict"]
    assert verdict["category"] == example["category"]
    assert verdict["score"] == f"{example['score']:.2f}"
    assert [c["score"] for c in verdict["criteria"]] == [f"{p:.2f}" for p in example["points"]]
    missing = {c["criterion_id"]: c["missing_evidence_ids"] for c in verdict["criteria"]}
    for criterion_id, ids in example["missing_evidence_ids"].items():
        assert missing[criterion_id] == ids


def test_lie_broken_in_interrogation_unlocks_deep_investigation_on_leaving(client):
    player = Player(client)
    player.start()
    player.investigate("A01")
    player.talk("NPC01")
    broken = player.present("E01").json()
    assert broken["phase_after"] == "INTERROGATION"
    assert player.leave().json()["phase_after"] == "DEEP_INVESTIGATION"


def test_victim_cannot_be_interrogated_and_unknown_npcs_are_hidden(client):
    player = Player(client)
    player.start()
    victim = player.talk("VICTIM")
    assert (victim.status_code, code(victim)) == (409, "NPC_UNAVAILABLE")
    unknown = player.talk("NPC09")
    assert (unknown.status_code, code(unknown)) == (404, "NPC_NOT_FOUND")


def test_progress_survives_a_backend_restart(client, migrated_url, monkeypatch):
    player = Player(client)
    player.start()
    player.investigate_all()
    run_path(player, PATHS["full_confession"][:3])
    assert player.leave().status_code == 200
    assert player.accuse().status_code == 201
    draft = {**CORRECT, "explanation": "草稿"}
    assert player.save_draft(draft).status_code == 200
    before = player.load()

    client.__exit__(None, None, None)
    with make_client(monkeypatch, migrated_url) as restarted:
        restarted.cookies = client.cookies
        current = restarted.get("/api/v1/sessions/current").json()
        assert current["session"] == before
        assert current["session"]["accusation_draft"] == draft
        player.client = restarted
        assert player.cancel_accusation().json()["phase_after"] == "DEEP_INVESTIGATION"
        assert player.talk("NPC01").status_code == 201
        assert player.present("E02").json()["data"]["outcome"]["reason_code"] == "EVIDENCE_RECORDED"
        admitted = player.present("E08").json()["data"]["outcome"]
        assert admitted["reason_code"] == "ADMISSION_RECORDED"
        assert player.accuse().status_code == 201
        assert player.load()["accusation_draft"] == draft
        assert player.submit().json()["data"]["verdict"]["category"] == "CORRECT"
