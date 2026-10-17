"""Home routing preserves authentication and no longer reads project/config data."""

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from landppt.auth.middleware import get_current_user_required
from landppt.main import root
from landppt.services import db_config_service
from landppt.web.route_modules import config_routes


@pytest.fixture(autouse=True)
def home_community(monkeypatch):
    service = SimpleNamespace(
        get_settings=AsyncMock(return_value={"sponsor_page_enabled": False}),
        get_public_sponsors=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(config_routes, "community_service", service)
    return service


def home_app():
    app = FastAPI()
    app.include_router(config_routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        id=17, username="home-user", is_admin=False
    )
    return app


def home_payload(response):
    script = re.search(
        r'<script id="antdData" type="application/json">(.*?)</script>',
        response.text,
        re.S,
    )
    return json.loads(script[1])


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
async def test_home_keeps_existing_required_user_dependency(home_community):
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
    home_community.get_settings.assert_not_awaited()


@pytest.mark.asyncio
async def test_home_publishes_only_six_public_sponsor_profiles(home_community):
    home_community.get_settings.return_value = {"sponsor_page_enabled": True}
    home_community.get_public_sponsors.return_value = [
        dict(
            nickname=f"支持者 {index}",
            avatar_url=None,
            bio="长期支持",
            link_url="https://example.invalid",
            id=index,
            is_active=True,
            amount="amount-not-needed-on-home",
            note="note-not-needed-on-home",
            private_secret="must-not-be-serialized",
        )
        for index in range(8)
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=home_app()), base_url="http://test"
    ) as client:
        response = await client.get("/home")
    assert response.status_code == 200
    sponsors = home_payload(response)["sponsors"]
    assert [row["nickname"] for row in sponsors] == [
        f"支持者 {index}" for index in range(6)
    ]
    assert all(
        set(row) == {"nickname", "avatar_url", "bio", "link_url"} for row in sponsors
    )
    for text in [
        "must-not-be-serialized",
        "amount-not-needed-on-home",
        "note-not-needed-on-home",
    ]:
        assert text not in response.text
    home_community.get_public_sponsors.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [False, True])
async def test_disabled_sponsor_page_hides_home_profiles_for_every_role(
    home_community, is_admin
):
    app = home_app()
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        id=17, username="home-user", is_admin=is_admin
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/home")
    assert response.status_code == 200
    assert home_payload(response)["sponsors"] == []
    home_community.get_public_sponsors.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_read", ["get_settings", "get_public_sponsors"])
async def test_sponsor_read_failure_does_not_break_home(home_community, failed_read):
    home_community.get_settings.return_value = {"sponsor_page_enabled": True}
    getattr(home_community, failed_read).side_effect = RuntimeError(
        "temporary sponsor failure"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=home_app()), base_url="http://test"
    ) as client:
        response = await client.get("/home")
    assert response.status_code == 200
    assert home_payload(response)["sponsors"] == []
    assert "temporary sponsor failure" not in response.text
