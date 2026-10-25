import pytest
from sqlalchemy.exc import OperationalError


DB_MODULE_NAME = "landppt.database.database"
MAIN_MODULE_NAME = "landppt.main"
LEGACY_POSTGRES_URL = "postgresql://landppt:landppt@postgres:5432/landppt"


def _reload_database_module(monkeypatch, load_isolated_module, database_url=None):
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)
    return load_isolated_module(DB_MODULE_NAME)


def test_database_module_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from landppt.core.config import AppConfig

    config = AppConfig()
    assert config.database_url == "sqlite:///./landppt.db"


def test_should_fallback_for_legacy_postgres_connectivity_error(monkeypatch, load_isolated_module):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    module = _reload_database_module(monkeypatch, load_isolated_module)

    err = OperationalError(
        "SELECT 1",
        {},
        Exception('could not translate host name "postgres" to address: Name or service not known'),
    )

    assert module._should_fallback_to_sqlite(err, LEGACY_POSTGRES_URL) is True


def test_should_not_fallback_for_explicit_custom_postgres_connectivity_error(monkeypatch, load_isolated_module):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    module = _reload_database_module(monkeypatch, load_isolated_module)
    custom_url = "postgresql://landppt:landppt@db.internal:5432/landppt"

    err = OperationalError(
        "SELECT 1",
        {},
        Exception("connection refused"),
    )

    assert module._should_fallback_to_sqlite(err, custom_url) is False


@pytest.mark.asyncio
async def test_startup_initialization_runs_in_order(monkeypatch):
    import landppt.main as main_module

    calls = []

    async def fake_run_startup_initialization():
        calls.append("run_startup_initialization")
        return True

    monkeypatch.setattr(main_module, "run_startup_initialization", fake_run_startup_initialization)

    await main_module.startup_event()

    assert calls == ["run_startup_initialization"]
