"""The Anthropic connection tests send a valid Messages API request."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import httpx
import pytest
from fastapi import FastAPI

from landppt.auth.middleware import get_current_user_required
from landppt.services import db_config_service
from landppt.web.route_modules import config_routes


class FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return {
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }

    async def text(self):
        return ""


@pytest.fixture
def anthropic_requests(monkeypatch):
    requests = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            requests.append({"url": url, **kwargs})
            return FakeResponse()

    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(
        config_routes, "_get_llm_timeout_seconds_for_user", AsyncMock(return_value=30)
    )
    monkeypatch.setattr(
        db_config_service,
        "get_db_config_service",
        lambda: SimpleNamespace(get_all_config=AsyncMock(return_value={})),
    )
    return requests


async def _post(path, body):
    app = FastAPI()
    app.include_router(config_routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        id=17, username="tester", is_admin=False
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/ai/providers/test", {"provider": "anthropic", "api_key": "sk-test"}),
        ("/api/ai/providers/anthropic/test", {"api_key": "sk-test"}),
    ],
)
async def test_anthropic_connection_test_sends_max_tokens(anthropic_requests, path, body):
    response = await _post(path, body)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert len(anthropic_requests) == 1
    request = anthropic_requests[0]
    assert request["url"] == "https://api.anthropic.com/v1/messages"
    payload = request["json"]
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["max_tokens"] > 0
