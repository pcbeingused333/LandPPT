import json
import types

import aiohttp
import pytest

from landppt.ai.base import AIMessage, MessageRole
from landppt.ai.providers import AnthropicProvider


def _sse(*events):
    return [f"data: {json.dumps(event)}\n".encode() for event in events]


def _text_delta(text):
    return {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": text},
    }


OVERLOADED = {
    "type": "error",
    "error": {"type": "overloaded_error", "message": "Overloaded"},
}


def _install_fake_session(monkeypatch, lines):
    posts = []

    class FakeContent:
        def __aiter__(self):
            return self._iterate()

        async def _iterate(self):
            for line in lines:
                yield line

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
            posts.append(headers)
            return FakeResponse()

    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)
    return posts


def _provider():
    return AnthropicProvider(
        {
            "api_key": "test-key",
            "base_url": "https://api.anthropic.com",
            "model": "claude-sonnet-5-5",
        }
    )


async def _collect(provider):
    chunks = []
    try:
        async for chunk in provider.stream_chat_completion(
            [AIMessage(role=MessageRole.USER, content="hello")]
        ):
            chunks.append(chunk)
    except Exception as exc:
        return chunks, exc
    return chunks, None


@pytest.mark.asyncio
async def test_error_event_after_text_fails_the_stream_without_a_retry(monkeypatch):
    posts = _install_fake_session(
        monkeypatch, _sse(_text_delta("Slide 1: "), OVERLOADED)
    )

    chunks, error = await _collect(_provider())

    assert chunks == ["Slide 1: "]
    assert str(error) == "Stream error overloaded_error: Overloaded"
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_error_event_before_any_text_tries_the_next_auth_method_then_fails(
    monkeypatch,
):
    posts = _install_fake_session(monkeypatch, _sse(OVERLOADED))

    chunks, error = await _collect(_provider())

    assert chunks == []
    assert str(error) == "Stream error overloaded_error: Overloaded"
    assert [list(headers)[-1] for headers in posts] == ["x-api-key", "Authorization"]


@pytest.mark.asyncio
async def test_complete_stream_still_succeeds(monkeypatch):
    posts = _install_fake_session(
        monkeypatch,
        _sse(
            _text_delta("Slide 1"),
            _text_delta(" done"),
            {"type": "message_stop"},
        ),
    )

    chunks, error = await _collect(_provider())

    assert chunks == ["Slide 1", " done"]
    assert error is None
    assert len(posts) == 1
