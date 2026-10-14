import pytest
from alembic import command
from alembic.config import Config
from player import CASE_VERSION, Player
from sqlalchemy import inspect, text

from backend.application.case import content_hash
from backend.config import PROJECT_ROOT
from backend.infrastructure.database.repositories.case_repository import CaseRepository

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


def test_topic_migration_round_trip_keeps_published_cases_and_saves(client, db, migrated_url):
    from conftest import alembic_config

    player = Player(client)
    player.start()
    for action in ("A01", "A02", "A03"):
        player.investigate(action)
    player.talk()
    player.ask_topic("Q01")
    config = alembic_config(migrated_url)
    command.downgrade(config, "0001")
    command.upgrade(config, "head")
    with db() as session:
        repository = CaseRepository(session)
        template = repository.find("case_001", CASE_VERSION)
        assert content_hash(repository.load_case(template)) == template.content_hash
    confirmed = player.contradict("K03", "E03").json()
    assert confirmed["data"]["outcome"]["reason_code"] == "CONTRADICTION_CONFIRMED"
