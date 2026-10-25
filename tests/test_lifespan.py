import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from landppt import main as main_module


@pytest.mark.asyncio
async def test_lifespan_swallows_cancelled_error_and_runs_shutdown():
    startup = AsyncMock()
    shutdown = AsyncMock()

    with (
        patch.object(main_module, "startup_event", new=startup),
        patch.object(main_module, "shutdown_event", new=shutdown),
    ):
        context_manager = main_module.lifespan(main_module.app)
        await context_manager.__aenter__()
        suppressed = await context_manager.__aexit__(
            asyncio.CancelledError,
            asyncio.CancelledError(),
            None,
        )

    assert suppressed is True
    startup.assert_awaited_once()
    shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_releases_resources_when_startup_fails(monkeypatch):
    startup = AsyncMock(side_effect=RuntimeError("startup failed"))
    shutdown = AsyncMock()
    monkeypatch.setattr(main_module, "startup_event", startup)
    monkeypatch.setattr(main_module, "shutdown_event", shutdown)
    with pytest.raises(RuntimeError, match="startup failed"):
        async with main_module.app.router.lifespan_context(main_module.app):
            pytest.fail("failed startup must not serve requests")
    shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_closes_database_even_if_cache_cleanup_fails(monkeypatch):
    from landppt.database import database
    from landppt.services import cache_service

    close_database = AsyncMock()
    monkeypatch.setattr(database, "close_db", close_database)
    monkeypatch.setattr(
        cache_service,
        "close_cache_service",
        AsyncMock(side_effect=RuntimeError("cache offline")),
    )
    await main_module.shutdown_event()
    close_database.assert_awaited_once()
