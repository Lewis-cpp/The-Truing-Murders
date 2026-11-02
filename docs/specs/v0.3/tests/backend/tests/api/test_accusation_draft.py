"""v0.3 acceptance: accusation drafts, incomplete submissions and the frozen result."""

import pytest
from player import CORRECT, EMPTY_DRAFT, Player

pytestmark = [pytest.mark.api, pytest.mark.integration]


def code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def player(client):
    player = Player(client)
    player.start()
    for action in ("A01", "A02", "A03"):
        player.investigate(action)
    return player


def test_draft_only_in_accusation(player):
    response = player.save_draft(EMPTY_DRAFT)
    assert (response.status_code, code(response)) == (409, "ACTION_NOT_ALLOWED")


def test_partial_draft_is_saved_kept_and_replayed(player):
    player.accuse()
    assert "SAVE_ACCUSATION_DRAFT" in player.load()["session"]["available_actions"]
    partial = {
        **EMPTY_DRAFT,
        "suspect_character_id": "NPC03",
        "ordered_process_step_ids": ["P_ENTER"],
    }
    version = player.version
    saved = player.save_draft(partial)
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"] == {"content": partial}
    assert saved.json()["result_state_version"] == version + 1
    same = player.save_draft(partial)
    assert same.json()["business_status"] == "NOOP"
    assert same.json()["result_state_version"] == version + 1
    assert player.get("/accusation-draft").json()["data"] == {"content": partial}
    assert player.cancel_accusation().json()["phase_after"] == "DEEP_INVESTIGATION"
    assert player.load()["accusation_draft"] == partial
    player.accuse()
    assert player.load()["accusation_draft"] == partial


@pytest.mark.parametrize(
    ("change", "status", "error"),
    [
        ({"motive_option_id": "M09"}, 422, "INVALID_ACCUSATION_OPTION"),
        ({"suspect_character_id": "VICTIM"}, 422, "INVALID_ACCUSATION_OPTION"),
        ({"ordered_process_step_ids": ["P_ENTER", "P_ENTER"]}, 422, "INVALID_ACCUSATION_OPTION"),
        ({"cited_evidence_ids": ["E05"]}, 422, "EVIDENCE_NOT_OWNED"),
        (
            {
                "ordered_process_step_ids": ["P_ENTER"],
                "cited_evidence_ids": ["E01"],
                "step_evidence_links": [{"step_id": "P_STAGE", "evidence_id": "E01"}],
            },
            422,
            "INVALID_ACCUSATION_OPTION",
        ),
    ],
)
def test_draft_references_are_checked(player, change, status, error):
    player.accuse()
    version = player.version
    response = player.save_draft({**EMPTY_DRAFT, **change})
    assert (response.status_code, code(response)) == (status, error)
    assert player.load()["session"]["state_version"] == version


def test_draft_needs_every_field(player):
    player.accuse()
    partial = {k: v for k, v in EMPTY_DRAFT.items() if k != "explanation"}
    response = player.save_draft(partial)
    assert (response.status_code, code(response)) == (422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "change",
    [
        {"suspect_character_id": None},
        {"weapon_option_id": None},
        {"motive_option_id": None},
        {"ordered_process_step_ids": []},
    ],
)
def test_incomplete_submission_is_rejected_and_keeps_the_game_open(player, change):
    player.accuse()
    content = {
        **CORRECT,
        "cited_evidence_ids": ["E01", "E02", "E03"],
        "step_evidence_links": [],
        **change,
    }
    response = player.submit(content)
    assert (response.status_code, code(response)) == (422, "ACCUSATION_INCOMPLETE")
    assert player.load()["session"]["phase"] == "ACCUSATION"


def test_submission_freezes_the_draft_and_cannot_repeat(player):
    player.accuse()
    player.save_draft({**EMPTY_DRAFT, "suspect_character_id": "NPC02"})
    submitted = {
        **CORRECT,
        "cited_evidence_ids": ["E01", "E02", "E03"],
        "step_evidence_links": [{"step_id": "P_ATTACK", "evidence_id": "E02"}],
        "explanation": "镇纸上的血印。",
    }
    closed = player.submit(submitted)
    assert closed.status_code == 201, closed.text
    assert closed.json()["data"]["content"] == submitted
    assert player.load()["accusation_draft"] == submitted
    again = player.submit(submitted)
    assert (again.status_code, code(again)) == (409, "ACCUSATION_ALREADY_SUBMITTED")
    late = player.save_draft(EMPTY_DRAFT)
    assert (late.status_code, code(late)) == (409, "ACTION_NOT_ALLOWED")
    assert player.get("/accusation").json()["data"]["content"] == submitted
