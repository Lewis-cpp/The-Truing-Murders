"""v0.6 acceptance: failure drills (spec section 4).

Faults are injected with PostgreSQL triggers, so the drills do not depend on code internals.
"""

import os
import shutil
import subprocess
import uuid
from contextlib import contextmanager

import pytest
from conftest import ORIGIN
from fastapi.testclient import TestClient
from player import Player
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from support.fakes import LLM_ENV, FakeGateway, install, ok

pytestmark = pytest.mark.integration


def code(response) -> str:
    return response.json()["error"]["code"]


def count(db, sql, **params):
    with db() as session:
        return session.execute(text(sql), params).scalar_one()


@contextmanager
def failing_message_inserts(db):
    """Every insert into conversation_message fails like a dropped connection."""
    with db.begin() as session:
        session.execute(
            text(
                "CREATE OR REPLACE FUNCTION drill_fail() RETURNS trigger AS $$ BEGIN RAISE"
                " EXCEPTION 'drill' USING ERRCODE = 'connection_failure'; END $$"
                " LANGUAGE plpgsql;"
                " CREATE TRIGGER drill_fail AFTER INSERT ON conversation_message"
                " FOR EACH ROW EXECUTE FUNCTION drill_fail();"
            )
        )
    try:
        yield
    finally:
        with db.begin() as session:
            session.execute(text("DROP TRIGGER IF EXISTS drill_fail ON conversation_message"))
            session.execute(text("DROP FUNCTION IF EXISTS drill_fail()"))


def test_a_presentation_failing_after_its_round_is_written_leaves_nothing(client, db):
    tolerant = TestClient(
        client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}, raise_server_exceptions=False
    )
    player = Player(client)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    before = player.load()
    key = uuid.uuid4()
    player.client = tolerant
    # httpx copies cookie jars on assignment, so the visitor cookie that start()
    # set must be re-synced after the swap, before the drill sends its request.
    tolerant.cookies = client.cookies
    with failing_message_inserts(db):
        failed = player.present("E01", key=key)
    assert (failed.status_code, code(failed)) == (503, "PERSISTENCE_UNAVAILABLE")
    assert failed.json()["error"]["retryable"] is True
    assert player.load() == before
    assert count(db, "SELECT count(*) FROM conversation") == 0
    assert count(db, "SELECT count(*) FROM rule_effect") == 0
    missing = tolerant.get(f"/api/v1/requests/{key}")
    assert (missing.status_code, code(missing)) == (404, "REQUEST_NOT_FOUND")

    retried = player.present("E01", key=key)
    assert retried.status_code == 201
    again = player.present("E01", key=key, version=retried.json()["state_version_before"])
    assert again.json() == retried.json()
    assert count(db, "SELECT count(*) FROM conversation") == 1
    assert player.npc("NPC01")["display_state"] == "NERVOUS"


def test_a_lost_response_after_commit_is_recovered_by_lookup(client, db):
    player = Player(client)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    key = uuid.uuid4()
    original = player.present("E01", key=key)  # pretend the browser never saw this
    record = client.get(f"/api/v1/requests/{key}").json()
    assert record["status"] == "COMMITTED"
    assert record["original_http_status"] == 201
    assert record["result"]["result_state_version"] == original.json()["result_state_version"]
    assert record["result"]["data"] == original.json()["data"]
    resent = player.present("E01", key=key, version=original.json()["state_version_before"])
    assert resent.json() == original.json()
    assert count(db, "SELECT count(*) FROM rule_effect WHERE effect_key = 'present:NPC01:E01'") == 1


def test_restarting_makes_the_old_round_stale_and_the_new_game_clean(db, migrated_url, monkeypatch):
    from conftest import make_client

    for key, value in LLM_ENV.items():
        monkeypatch.setenv(key, value)
    with make_client(monkeypatch, migrated_url) as llm_client:
        holder = {}

        def restart_then_answer(call):
            player = holder["player"]
            response = player.write(
                "POST",
                "/api/v1/sessions",
                {
                    "case_id": "case_001",
                    "case_version": player.load()["session"]["case_version"],
                    "replaces_session_id": holder["old"],
                    "confirm_restart": True,
                },
            )
            assert response.status_code == 201
            return ok("属于旧局的迟到回答。")

        gateway = FakeGateway(restart_then_answer)
        dispatcher = install(llm_client, gateway)
        player = Player(llm_client)
        player.start()
        player.investigate_all()
        player.talk("NPC01")
        holder.update(player=player, old=player.session_id)
        old_round = player.chat("旧局的问题").json()["data"]["conversation_id"]
        dispatcher.run_all()
        assert player.session_id != holder["old"]
        old = llm_client.get(f"/api/v1/sessions/{holder['old']}/conversations/{old_round}")
        assert old.json()["data"]["generation_status"] == "STALE"
        assert "迟到回答" not in old.text
        new_history = player.get("/npcs/NPC01/conversations").json()["data"]["items"]
        assert new_history == []
        assert (
            count(
                db,
                "SELECT count(*) FROM llm_attempt"
                " WHERE usage_status = 'KNOWN' AND validation_status = 'STALE'",
            )
            == 1
        )


def _pg_tool(name):
    path = shutil.which(name)
    if not path:
        return None
    version = subprocess.run([path, "--version"], capture_output=True, text=True).stdout
    return path if " 18." in version else None


@pytest.mark.skipif(
    not (_pg_tool("pg_dump") and _pg_tool("pg_restore")),
    reason="needs pg_dump/pg_restore 18 on PATH; record the manual drill in the delivery notes",
)
def test_backup_and_restore_keep_an_open_game_playable(client, db, migrated_url, tmp_path):
    player = Player(client)
    player.start()
    player.investigate_all(["A01", "A02", "A03"])
    player.talk("NPC01")
    player.present("E01")
    before = player.load()
    url = make_url(migrated_url)
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    target = ["-h", url.host, "-p", str(url.port or 5432), "-U", url.username]
    dump = tmp_path / "backup.dump"
    subprocess.run(
        [_pg_tool("pg_dump"), "-Fc", *target, "-d", url.database, "-f", str(dump)],
        check=True,
        env=env,
    )
    engine = create_engine(migrated_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    subprocess.run(
        [_pg_tool("pg_restore"), *target, "-d", url.database, "--no-owner", str(dump)],
        check=True,
        env=env,
    )
    assert player.load() == before
    assert player.present("E03").json()["data"]["outcome"]["reason_code"] == "ADMISSION_RECORDED"
