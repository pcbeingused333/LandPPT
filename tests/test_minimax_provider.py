"""MiniMax connects through explicit OpenAI-compatible or managed configuration.

The built-in preset was removed during provider consolidation. Exercise the
supported paths without reviving vendor-specific environment variables.
"""

import json
import os

import httpx
import openai
import pytest

from landppt.ai.base import AIMessage, MessageRole
from landppt.ai.providers import AIProviderFactory, OpenAIProvider
from landppt.core import config as config_module

BASE_URL = "https://api.minimax.io/v1"
MODEL = "MiniMax-M2.7"  # Explicit fixture model, not a built-in default.


@pytest.fixture
def compatible_settings(monkeypatch, tmp_path):
    # reload_ai_config also reads .env; never consume a developer's local file.
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "OPENAI_API_KEY": "test-key",
        "OPENAI_BASE_URL": BASE_URL,
        "OPENAI_MODEL": MODEL,
        "DEFAULT_AI_PROVIDER": "openai",
    }.items():
        monkeypatch.setenv(name, value)
    settings = config_module.AIConfig(
        temperature=0.7,
        max_tokens=16384,
        default_model_provider=None,
        default_model_name=None,
    )
    # Reload tests must not mutate the singleton retained by other services.
    monkeypatch.setattr(config_module, "ai_config", settings)
    return settings


def test_legacy_name_is_not_advertised_or_silently_resolved(compatible_settings):
    assert "minimax" not in AIProviderFactory.get_available_providers()
    with pytest.raises(ValueError, match="Unknown provider: minimax"):
        AIProviderFactory.create_provider(
            "minimax", compatible_settings.get_provider_config("openai")
        )


def test_compatible_config_keeps_explicit_endpoint_model_and_key(compatible_settings):
    config = compatible_settings.get_provider_config("openai")
    assert config["api_key"] == "test-key"
    assert config["base_url"] == BASE_URL
    assert config["model"] == MODEL
    assert config["max_tokens"] == 16384


@pytest.mark.parametrize(
    "field,value",
    [
        ("api_key", "other-test-key"),
        ("base_url", "https://proxy.example.test/v1"),
        ("model", "user-selected-minimax-model"),
    ],
)
def test_compatible_environment_overrides(
    compatible_settings, monkeypatch, field, value
):
    monkeypatch.setenv("OPENAI_" + field.upper(), value)
    assert config_module.AIConfig().get_provider_config("openai")[field] == value


@pytest.mark.parametrize(
    "key,available", [(None, False), ("", False), ("test-key", True)]
)
def test_compatible_availability_requires_a_key(compatible_settings, key, available):
    compatible_settings.openai_api_key = key
    assert compatible_settings.is_provider_available("openai") is available
    assert ("openai" in compatible_settings.get_available_providers()) is available


@pytest.mark.parametrize("temperature", [0.0, 0.7, 1.0])
def test_compatible_temperature_is_explicit(compatible_settings, temperature):
    compatible_settings.temperature = temperature
    assert (
        compatible_settings.get_provider_config("openai")["temperature"] == temperature
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("api_key", "new-test-key"),
        ("base_url", "https://proxy.example.test/v1"),
        ("model", "user-selected-minimax-model"),
    ],
)
def test_reload_updates_compatible_settings_without_changing_identity(
    compatible_settings, monkeypatch, field, value
):
    monkeypatch.setenv("OPENAI_" + field.upper(), value)
    config_module.reload_ai_config()
    assert config_module.ai_config is compatible_settings
    assert getattr(compatible_settings, "openai_" + field) == value


def test_roles_preserve_managed_identity_until_user_resolution(compatible_settings):
    default = compatible_settings.get_model_config_for_role("default")
    assert default["provider"] == "openai" and default["model"] == MODEL
    managed = compatible_settings.get_model_config_for_role(
        "default", provider_override="custom:minimax"
    )
    assert managed["provider"] == "custom:minimax" and managed["model"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["openai", "custom:minimax"])
async def test_factory_uses_compatible_adapter_and_copies_config(
    compatible_settings, name
):
    config = compatible_settings.get_provider_config("openai")
    provider = AIProviderFactory.create_provider(name, config, use_cache=False)
    try:
        assert isinstance(provider, OpenAIProvider)
        assert provider.model == MODEL and provider.config["base_url"] == BASE_URL
        assert "managed_provider" not in config
        if name.startswith("custom:"):
            assert provider.config["managed_provider"] is True
    finally:
        await provider.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["openai", "custom:minimax"])
@pytest.mark.parametrize("stream", [False, True])
async def test_requests_preserve_destination_parameters_and_streaming(
    compatible_settings, name, stream
):
    config = compatible_settings.get_provider_config("openai")
    provider = AIProviderFactory.create_provider(name, config, use_cache=False)
    await provider.client.close()
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == BASE_URL + "/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == MODEL and body["temperature"] == 0.7
        if stream:
            chunk = {
                "id": "test",
                "model": MODEL,
                "choices": [
                    {"index": 0, "delta": {"content": "hello"}, "finish_reason": None}
                ],
            }
            return httpx.Response(
                200,
                text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n",
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={
                "id": "test",
                "model": MODEL,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    provider.client = openai.AsyncOpenAI(
        api_key="test-key",
        base_url=BASE_URL,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    try:
        messages = [AIMessage(role=MessageRole.USER, content="Hi")]
        if stream:
            result = "".join(
                [part async for part in provider.stream_chat_completion(messages)]
            )
            assert calls[0]["stream"] is True
        else:
            result = (await provider.chat_completion(messages)).content
        assert result == "hello" and len(calls) == 1
    finally:
        await provider.client.close()


@pytest.mark.skipif(
    not os.environ.get("MINIMAX_API_KEY"),
    reason="MINIMAX_API_KEY not set; optional live API checks",
)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stream,temperature", [(False, 0.7), (True, 0.7), (False, 0.0)]
)
async def test_live_minimax_through_compatible_adapter(stream, temperature):
    provider = AIProviderFactory.create_provider(
        "openai",
        {
            "api_key": os.environ["MINIMAX_API_KEY"],
            "base_url": BASE_URL,
            "model": MODEL,
            "max_tokens": 64,
            "temperature": temperature,
        },
        use_cache=False,
    )
    try:
        messages = [AIMessage(role=MessageRole.USER, content="Reply OK.")]
        if stream:
            assert "".join(
                [part async for part in provider.stream_chat_completion(messages)]
            )
        else:
            assert (await provider.chat_completion(messages)).content
    finally:
        await provider.client.close()
