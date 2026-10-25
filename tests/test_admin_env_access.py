"""The retained compatibility endpoints must not expose or overwrite env to users."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize("role,status", [("guest", 401), ("user", 403), ("admin", 200)])
async def test_env_read_and_write_require_admin(role, status, tmp_path, monkeypatch):
    from landppt.auth.middleware import get_current_user_required
    from landppt.web import admin_routes

    env_path = tmp_path / ".env"
    env_path.write_text("TEST_SETTING=original\n", encoding="utf-8")
    reload_runtime = AsyncMock()
    monkeypatch.setattr(admin_routes, "_get_env_file_path", lambda: env_path)
    monkeypatch.setattr(admin_routes, "_reload_runtime_from_env", reload_runtime)

    async def identity():
        if role == "guest":
            raise HTTPException(401, "Sign in")
        return SimpleNamespace(id=1, is_admin=role == "admin")

    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[get_current_user_required] = identity
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        read = await client.get("/admin/api/system-env-file")
        assert read.status_code == status
        write = await client.post(
            "/admin/api/system-env-file", json={"content": "TEST_SETTING=changed\r\n"}
        )
        assert write.status_code == status
    if role == "admin":
        assert read.json()["content"] == "TEST_SETTING=original\n"
        assert env_path.read_text(encoding="utf-8") == "TEST_SETTING=changed\n"
        reload_runtime.assert_awaited_once()
    else:
        assert "original" not in read.text
        assert env_path.read_text(encoding="utf-8") == "TEST_SETTING=original\n"
        reload_runtime.assert_not_awaited()
