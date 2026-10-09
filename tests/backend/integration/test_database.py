import pytest
from alembic import command
from alembic.config import Config
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
