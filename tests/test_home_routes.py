"""Home routing preserves authentication and no longer reads project/config data."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from landppt.auth.middleware import get_current_user_required
from landppt.main import root
from landppt.services import db_config_service
from landppt.web.route_modules import config_routes


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [False, True])
async def test_returning_user_gets_showcase_without_project_or_config_lookup(
    monkeypatch, is_admin
):
    app = FastAPI()
    app.include_router(config_routes.router)
    app.add_api_route("/", root)
    user = SimpleNamespace(id=17, username="home-user", is_admin=is_admin)
    app.dependency_overrides[get_current_user_required] = lambda: user
    list_projects = AsyncMock(
        side_effect=AssertionError("Homepage must not list private projects")
    )
    monkeypatch.setattr(
        config_routes.ppt_service.project_manager, "list_projects", list_projects
    )
    monkeypatch.setattr(
        db_config_service,
        "get_db_config_service",
        lambda: pytest.fail("Homepage must not load provider secrets"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert response.url.path == "/home"
    assert [item.headers.get("location") for item in response.history] == ["/home"]
    assert '"page": "home"' in response.text
    assert '"username": "home-user"' in response.text
    assert "aiProvider" not in response.text
    list_projects.assert_not_awaited()


@pytest.mark.asyncio
async def test_home_keeps_existing_required_user_dependency():
    app = FastAPI()
    app.include_router(config_routes.router)

    def unauthenticated():
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[get_current_user_required] = unauthenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/home")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
