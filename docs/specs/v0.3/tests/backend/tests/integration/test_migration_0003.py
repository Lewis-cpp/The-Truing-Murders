"""v0.3 acceptance: migration 0003 keeps v0.2 saves, and they stay readable but unsupported."""

import json
from pathlib import Path

import pytest
from alembic import command
from conftest import ORIGIN, alembic_config
from fastapi.testclient import TestClient
from player import Player
from sqlalchemy import create_engine, inspect, text

from backend.application.case import default_case_path
from backend.application.catalog import import_case
from backend.infrastructure.database.models import Base

pytestmark = pytest.mark.integration

LEGACY = Path(__file__).resolve().parents[1] / "data/legacy"
META = json.loads((LEGACY / "v0_2_slice_save.json").read_text(encoding="utf-8"))


@pytest.fixture
def legacy_database(migrated_url):
    """Rebuilds the schema at 0002, restores a v0.2 save, then upgrades to head."""
    config = alembic_config(migrated_url)
    command.downgrade(config, "base")
    command.upgrade(config, "0002")
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        for line in (LEGACY / "v0_2_slice_save.sql").read_text(encoding="utf-8").splitlines():
            if line.strip():
                connection.exec_driver_sql(line)
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables}"))
        engine.dispose()


def count(engine, table):
    with engine.connect() as connection:
        return connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()


def test_upgrade_keeps_every_legacy_row(legacy_database):
    engine = legacy_database
    assert count(engine, "game_session") == 1
    assert count(engine, "action_request") == 7
    assert count(engine, "player_evidence") == 3
    assert count(engine, "npc_state") == 1
    tables = set(inspect(engine).get_table_names())
    assert {"conversation", "conversation_message", "relationship", "timeline_event"} <= tables
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT phase, state_version FROM game_session WHERE session_id = :id"),
            {"id": META["session_id"]},
        ).one()
    assert tuple(row) == ("INTERROGATION", META["state_version"])


def test_legacy_save_is_kept_but_cannot_continue(legacy_database, migrated_url, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    import_case(sessionmaker(legacy_database, expire_on_commit=False), default_case_path())
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    monkeypatch.setenv("ALLOWED_ORIGINS", f'["{ORIGIN}"]')
    from backend.main import app

    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        client.cookies.set("visitor_token", META["visitor_token"])
        current = client.get("/api/v1/sessions/current")
        assert current.status_code == 409
        error = current.json()["error"]
        assert error["code"] == "SAVE_VERSION_UNSUPPORTED"
        assert error["details"] == {
            "session_id": META["session_id"],
            "state_version": META["state_version"],
        }
        cases = client.get("/api/v1/cases").json()["items"]
        assert [(c["case_id"], c["case_version"]) for c in cases] == [("case_001", "3-full")]

        player = Player(client)
        response = player.write(
            "POST",
            "/api/v1/sessions",
            {
                "case_id": "case_001",
                "case_version": "3-full",
                "replaces_session_id": META["session_id"],
                "confirm_restart": True,
            },
            version=META["state_version"],
        )
        assert response.status_code == 201, response.text
        assert player.load()["session"]["case_version"] == "3-full"
    assert count(legacy_database, "game_session") == 2


def test_head_downgrades_to_0002_and_back_on_an_empty_database(migrated_url):
    config = alembic_config(migrated_url)
    command.downgrade(config, "0002")
    command.upgrade(config, "head")
    command.check(config)
