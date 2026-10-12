import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.application.case import default_case_path
from backend.application.catalog import import_case
from backend.config import PROJECT_ROOT, Settings
from backend.infrastructure.database.models import Base

ORIGIN = "https://testserver"


class DatabaseTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    test_database_url: PostgresDsn


def _test_database_url() -> str:
    url = str(DatabaseTestSettings().test_database_url)
    database = make_url(url).database
    if not database or not database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to a database ending in _test")
    if make_url(url) == make_url(str(Settings().database_url)):
        pytest.fail("Test and development database URLs must be different")
    return url


def alembic_config(url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture
def database_url():
    return _test_database_url()


@pytest.fixture
def engine(database_url):
    engine = create_engine(database_url, connect_args={"connect_timeout": 3})
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def migrated_url():
    """Rebuild the test schema once from the migrations, never from metadata.create_all."""
    url = _test_database_url()
    config = alembic_config(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return url


@pytest.fixture
def db(migrated_url):
    """A migrated test database holding exactly the published W1 slice."""
    engine = create_engine(migrated_url, connect_args={"connect_timeout": 3})
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables}"))
    sessions = sessionmaker(engine, expire_on_commit=False)
    import_case(sessions, default_case_path())
    try:
        yield sessions
    finally:
        engine.dispose()


def make_client(monkeypatch, url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("ALLOWED_ORIGINS", f'["{ORIGIN}"]')
    from backend.main import app

    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


@pytest.fixture
def client(db, migrated_url, monkeypatch):
    with make_client(monkeypatch, migrated_url) as client:
        yield client
