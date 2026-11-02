import pytest
from alembic import command
from alembic.config import Config
from player import Player
from sqlalchemy import inspect, text

from backend.config import PROJECT_ROOT

pytestmark = pytest.mark.integration


def test_postgresql_version_jsonb_and_transaction_rollback(engine):
    with engine.connect() as connection:
        version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
        assert 180000 <= version < 190000
        assert connection.execute(text("SELECT '{\"connected\": true}'::jsonb")).scalar_one() == {
            "connected": True
        }
        connection.execute(text("CREATE TEMP TABLE environment_probe (value integer)"))
        connection.commit()

        transaction = connection.begin()
        connection.execute(text("INSERT INTO environment_probe VALUES (1)"))
        transaction.rollback()
        assert connection.execute(text("SELECT count(*) FROM environment_probe")).scalar_one() == 0


def test_migration_environment_connects_to_test_database(monkeypatch, database_url, engine):
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    assert inspect(engine).has_table("alembic_version")


def test_migrations_match_models_and_downgrade_cleanly(migrated_url):
    from conftest import alembic_config

    config = alembic_config(migrated_url)
    command.check(config)  # raises if models and migrations differ
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


def test_topic_migration_round_trip_keeps_saves_and_testimony_marks(client, db, migrated_url):
    """A downgrade to 0002 and back keeps save rows; 0002 re-marks ASKED secrets on the way up."""
    from conftest import alembic_config

    player = Player(client)
    player.start()
    player.investigate_all()
    player.talk("NPC01")
    player.ask_topic("Q01")
    config = alembic_config(migrated_url)
    command.downgrade(config, "0002")
    command.upgrade(config, "head")
    with db() as session:
        asked = (
            session.execute(
                text(
                    "SELECT secret_id FROM character_secret WHERE disclosure = 'ASKED'"
                    " ORDER BY secret_id"
                )
            )
            .scalars()
            .all()
        )
        # The full downgrade to an empty database is covered by the v0.3 migration test;
        # this cycle must keep every save row and the testimony disclosures.
        assert asked == ["K03", "K07", "K08", "K09", "K10"]
        assert session.execute(text("SELECT count(*) FROM game_session")).scalar_one() == 1
        assert session.execute(text("SELECT count(*) FROM npc_state")).scalar_one() == 4
        assert session.execute(text("SELECT count(*) FROM game_event_log")).scalar_one() >= 13
