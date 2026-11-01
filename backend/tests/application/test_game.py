"""Ported v0.2 engine checks for the local CLI game, on the full case."""

import pytest

from backend.application.case import load_case
from backend.application.game import Game
from backend.domain.models import Accusation, GameError, Phase, StepEvidenceLink

pytestmark = pytest.mark.unit


@pytest.fixture
def game():
    return Game(load_case())


def accusation(**changes):
    fields = dict(
        culprit="NPC01",
        weapon="W01",
        motive="M01",
        steps=("P_ENTER", "P_ATTACK", "P_STAGE"),
        cited_evidence_ids=(),
        evidence_links=(),
    )
    return Accusation(**(fields | changes))


@pytest.mark.parametrize(
    "action",
    [
        lambda g: g.present("NPC01", "E01"),
        lambda g: g.ask("问题"),
        lambda g: g.inspect("UNKNOWN"),
        lambda g: g.talk("VICTIM"),
        lambda g: g.submit(accusation()),
        lambda g: g.review(),
        lambda g: g.back(),
    ],
)
def test_rejected_initial_actions_are_atomic(game, action):
    before = game.state
    with pytest.raises(GameError):
        action(game)
    assert game.state == before


def test_illegal_interrogation_targets_and_unheld_evidence_are_atomic(game):
    game.inspect("A01")
    game.talk("NPC01")
    before = game.state
    for action in (
        lambda: game.inspect("A05"),
        lambda: game.present("NPC02", "E01"),
        lambda: game.present("NPC01", "E03"),
    ):
        with pytest.raises(GameError):
            action()
        assert game.state == before


def test_accusation_can_be_cancelled_without_confession_or_evidence(game):
    game.accuse()
    before = game.state
    for action in (lambda: game.talk("NPC01"), lambda: game.inspect("A01")):
        with pytest.raises(GameError):
            action()
        assert game.state == before
    game.back()
    assert game.state.phase == Phase.INVESTIGATION
    assert not game.state.evidence_ids


@pytest.mark.parametrize(
    "changes",
    [
        {"culprit": "UNKNOWN"},
        {"weapon": "UNKNOWN"},
        {"motive": "UNKNOWN"},
        {"steps": ()},
        {"steps": ("P_ENTER", "P_ENTER")},
        {"cited_evidence_ids": ("E05",)},
        {"cited_evidence_ids": ("E01", "E01")},
    ],
)
def test_invalid_submission_does_not_close_or_change_state(game, changes):
    game.inspect("A01")
    game.accuse()
    before = game.state
    with pytest.raises(GameError):
        game.submit(accusation(**changes))
    assert game.state == before
    assert game.state.verdict is None


@pytest.mark.parametrize("step,evidence", [("P_CUT_POWER", "E01"), ("P_ENTER", "E02")])
def test_links_must_belong_to_submitted_steps_and_citations(game, step, evidence):
    game.inspect("A01")
    game.inspect("A02")
    game.accuse()
    before = game.state
    with pytest.raises(GameError):
        game.submit(
            accusation(
                cited_evidence_ids=("E01",),
                evidence_links=(StepEvidenceLink(step_id=step, evidence_id=evidence),),
            )
        )
    assert game.state == before


def test_closure_freezes_input_and_review_does_not_grant_missing_evidence(game):
    game.inspect("A01")
    game.accuse()
    game.submit(accusation(steps=("P_ENTER",), cited_evidence_ids=("E01",)))
    frozen = game.state
    assert game.state.verdict.score == 60
    assert "truth" in game.view()
    for action in (
        lambda: game.inspect("A01"),
        lambda: game.talk("NPC01"),
        lambda: game.back(),
        lambda: game.accuse(),
        lambda: game.submit(accusation()),
        lambda: game.present("NPC01", "E01"),
    ):
        with pytest.raises(GameError):
            action()
        assert game.state == frozen
    first = game.review()
    assert game.review() == first
    assert game.state == frozen
    game.finish()
    assert game.review() == first
    assert game.state.verdict is frozen.verdict


def test_separate_games_and_read_only_actions_do_not_share_or_change_state(game):
    other = Game(load_case())
    game.inspect("A01")
    assert not other.state.evidence_ids
    before = game.state
    game.view()
    game.view()
    assert game.state == before


def test_alternate_investigation_source_does_not_duplicate_evidence():
    case = load_case()
    alternate = case.scenes[0].actions[0].model_copy(update={"id": "A99"})
    scene = case.scenes[0].model_copy(update={"actions": (*case.scenes[0].actions, alternate)})
    case = case.model_copy(update={"scenes": (scene, *case.scenes[1:])})
    game = Game(case)
    game.inspect("A01")
    assert "没有重复发放" in game.inspect("A99")
    assert game.state.evidence_ids == {"E01"}
    assert game.state.completed_actions == {"A01", "A99"}
    before = game.state
    game.inspect("A99")
    assert game.state == before


def test_view_is_an_allowlist_without_hidden_content(game):
    initial = str(game.view())
    case = game.case
    assert "truth" not in game.view()
    assert "admission_pressure_min" not in initial
    assert case.lies[1].statements.admitted not in initial
    assert case.evidence[0].content not in initial
    assert all(scene["id"] == "S01" for scene in game.view()["scenes"])
