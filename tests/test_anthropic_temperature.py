import json
import sys
import types

import aiohttp
import pytest

from landppt.ai.base import AIMessage, MessageRole
from landppt.ai.providers import AnthropicProvider

REJECTING_MODELS = [
    "claude-opus-4-7",
    "claude-opus-4-7-20261015",
    "claude-opus-4-10",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "claude-fable-5-1",
    "claude-mythos-preview",
]
ACCEPTING_MODELS = [
    "claude-opus-4-6",
    "claude-opus-4-1-20250805",
    "claude-opus-4-20250514",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-3-5-haiku-latest",
]
MESSAGES = [AIMessage(role=MessageRole.USER, content="hello")]


def _provider(model):
    return AnthropicProvider(
        {"api_key": "test-key", "base_url": "https://api.anthropic.com", "model": model}
    )


async def _messages_request(monkeypatch, model):
    calls = []

    class FakeMessages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(
                model=kwargs["model"],
                content=[types.SimpleNamespace(type="text", text="ok")],
                stop_reason="end_turn",
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setitem(
        sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=FakeAsyncAnthropic)
    )
    await _provider(model).chat_completion(
        MESSAGES, tools=[{"name": "noop", "input_schema": {"type": "object"}}]
    )
    return calls[0]


async def _stream_request(monkeypatch, model):
    bodies = []

    class FakeContent:
        def __aiter__(self):
            return self._iterate()

        async def _iterate(self):
            yield f"data: {json.dumps({'type': 'message_stop'})}\n".encode()

    class FakeResponse:
        status = 200
        content = FakeContent()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None):
            bodies.append(json)
            return FakeResponse()

    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)
    async for _ in _provider(model).stream_chat_completion(MESSAGES):
        pass
    return bodies[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", REJECTING_MODELS)
async def test_temperature_is_omitted_for_models_that_reject_it(monkeypatch, model):
    assert "temperature" not in await _messages_request(monkeypatch, model)
    assert "temperature" not in await _stream_request(monkeypatch, model)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ACCEPTING_MODELS)
async def test_temperature_is_kept_for_older_models(monkeypatch, model):
    assert (await _messages_request(monkeypatch, model))["temperature"] == 0.7
    assert (await _stream_request(monkeypatch, model))["temperature"] == 0.7
