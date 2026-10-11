import pytest
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from backend.config import PROJECT_ROOT, Settings


class DatabaseTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    test_database_url: PostgresDsn


@pytest.fixture
def database_url():
    url = str(DatabaseTestSettings().test_database_url)
    database = make_url(url).database
    if not database or not database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to a database ending in _test")
    if make_url(url) == make_url(str(Settings().database_url)):
        pytest.fail("Test and development database URLs must be different")
    return url


@pytest.fixture
def engine(database_url):
    engine = create_engine(database_url, connect_args={"connect_timeout": 3})
    try:
        yield engine
    finally:
        engine.dispose()
