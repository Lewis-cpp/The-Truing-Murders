import json
import uuid
from datetime import UTC, datetime

import pytest
from conftest import ORIGIN
from fastapi.testclient import TestClient
from player import Player
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.application.case import content_hash, default_case_path, load_case
from backend.application.catalog import import_case
from backend.infrastructure.database.models import (
    ActionRequest,
    CaseTemplate,
    GameEventLog,
    GameSession,
    PlayerEvidence,
    RuleEffect,
)
from backend.infrastructure.database.repositories.case_repository import CaseRepository
from backend.infrastructure.database.repositories.session_repository import SessionRepository

pytestmark = pytest.mark.integration


def count(db, table) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(table))


def test_database_definition_reproduces_the_reviewed_case(db):
    case = load_case()
    with db() as session:
        template = CaseRepository(session).find("case_001", "1-slice")
        assert template.status == "PUBLISHED"
        assert template.content_hash == content_hash(case)
        assert (
            CaseRepository(session).load_case(template).model_dump()["truth"]
            == (case.model_dump()["truth"])
        )
        assert content_hash(CaseRepository(session).load_case(template)) == content_hash(case)


def test_published_version_is_never_overwritten(db, tmp_path):
    raw = json.loads(default_case_path().read_text())
    raw["title"] = "被篡改的标题"
    path = tmp_path / "case.json"
    path.write_text(json.dumps(raw, ensure_ascii=False))
    with pytest.raises(ValueError, match="已发布且内容不同"):
        import_case(db, path)
    assert import_case(db, default_case_path()).created is False
    with db() as session:
        assert session.scalar(select(CaseTemplate.title)) == "停电之夜"


def test_duplicate_json_keys_are_rejected(tmp_path):
    text_value = default_case_path().read_text().replace('"title"', '"title": "x", "title"', 1)
    path = tmp_path / "case.json"
    path.write_text(text_value)
    with pytest.raises(ValueError, match="重复的 JSON 键"):
        load_case(path)


def test_failure_after_writing_evidence_rolls_back_everything(client, db, monkeypatch):
    # Serve the unexpected error as an HTTP 500 instead of re-raising it into the test.
    client = TestClient(
        client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}, raise_server_exceptions=False
    )
    player = Player(client)
    player.start()
    requests_before = count(db, ActionRequest)

    def explode(*_args, **_kwargs):
        raise RuntimeError("injected failure after player_evidence insert")

    monkeypatch.setattr(SessionRepository, "_add_effects", explode)
    key = uuid.uuid4()
    failed = player.investigate("A01", key=key)
    assert (failed.status_code, failed.json()["error"]["code"]) == (500, "INTERNAL_ERROR")
    assert count(db, PlayerEvidence) == 0
    assert count(db, ActionRequest) == requests_before
    assert count(db, GameEventLog) == 1  # only the session creation event
    assert player.load()["session"]["state_version"] == 1
    assert client.get(f"/api/v1/requests/{key}").status_code == 404

    monkeypatch.undo()
    retried = player.investigate("A01", key=key, version=1)
    assert retried.status_code == 201
    assert count(db, PlayerEvidence) == 1


def test_database_outage_is_reported_as_unsaved_and_retryable(client, monkeypatch):
    player = Player(client)
    player.start()

    def unavailable(*_args, **_kwargs):
        raise OperationalError("SELECT", {}, Exception("connection refused"))

    monkeypatch.setattr(SessionRepository, "get_session", unavailable)
    response = player.investigate("A01")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PERSISTENCE_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True


def test_composite_keys_and_uniqueness_hold_in_postgresql(client, db, tmp_path):
    player = Player(client)
    player.start()
    player.investigate("A01")
    player.talk()
    player.present("E01")
    raw = json.loads(default_case_path().read_text())
    raw["version"] = "2-slice"
    path = tmp_path / "case.json"
    path.write_text(json.dumps(raw, ensure_ascii=False))
    other_template = uuid.UUID(import_case(db, path).template_id)
    session_id = uuid.UUID(player.session_id)
    now = datetime.now(UTC)

    def violates(statement) -> None:
        with db() as session, pytest.raises(IntegrityError):
            with session.begin():
                statement(session)

    with db() as session:
        event_id = session.scalar(
            select(GameEventLog.event_id).where(GameEventLog.session_id == session_id).limit(1)
        )
        effect = session.scalars(select(RuleEffect)).first()

    # Another version's evidence cannot be attached to this game.
    violates(
        lambda s: s.add(
            PlayerEvidence(
                session_id=session_id,
                template_id=other_template,
                evidence_id="E02",
                discovered_at=now,
                acquired_event_id=event_id,
                credibility="VERIFIED",
                updated_at=now,
            )
        )
    )
    # One-time effects and held evidence are unique per game.
    violates(
        lambda s: s.add(
            RuleEffect(session_id=session_id, effect_key=effect.effect_key, event_id=event_id)
        )
    )
    violates(lambda s: s.execute(text("INSERT INTO player_evidence SELECT * FROM player_evidence")))
    # INTERROGATION requires an active NPC, and the NPC must belong to the same version.
    violates(
        lambda s: s.execute(
            text("UPDATE game_session SET active_npc_id = NULL WHERE phase = 'INTERROGATION'")
        )
    )
    violates(
        lambda s: s.execute(
            text("UPDATE game_session SET active_npc_id = 'NPC99' WHERE session_id = :id"),
            {"id": session_id},
        )
    )


def test_only_one_formal_accusation_per_game(client, db):
    player = Player(client)
    player.start()
    player.accuse()
    player.submit(
        {
            "suspect_character_id": "NPC01",
            "weapon_option_id": "W01",
            "motive_option_id": "M01",
            "ordered_process_step_ids": ["P_ENTER"],
            "cited_evidence_ids": [],
            "step_evidence_links": [],
            "explanation": "",
        }
    )
    with db() as session, pytest.raises(IntegrityError), session.begin():
        session.execute(text("INSERT INTO accusation SELECT * FROM accusation"))
    with db() as session:
        row = session.scalar(select(GameSession))
        assert row.phase == "REVIEW" and row.closed_at is not None
