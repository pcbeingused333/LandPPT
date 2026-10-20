import pytest

from landppt.services.provider_test_utils import build_google_test_payload


class FakeResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    status = 200

    async def json(self):
        return {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 3},
        }

    async def text(self):
        return ""


@pytest.fixture
def rest_calls(monkeypatch):
    import aiohttp

    calls = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, params=None, json=None, headers=None):
            calls.append(json)
            return FakeResponse()

    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)
    return calls


def _google_provider(model, base_url="https://mirror.example.com/prefix"):
    from landppt.ai.providers import GoogleProvider

    # A base_url with a path prefix forces the REST transport; the official
    # endpoint uses the SDK.
    return GoogleProvider({"api_key": "test-key", "base_url": base_url, "model": model})


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gemini-3.8-flash", "gemini-3.6-pro", "models/gemini-3.8-flash"])
async def test_rest_request_omits_sampling_params_for_gemini_3(rest_calls, model):
    await _google_provider(model).text_completion("hello", temperature=0.2, top_p=0.9)

    generation_config = rest_calls[0]["generationConfig"]
    assert "temperature" not in generation_config
    assert "topP" not in generation_config


@pytest.mark.asyncio
async def test_rest_request_keeps_sampling_params_for_older_models(rest_calls):
    await _google_provider("gemini-2.5-flash").text_completion("hello", temperature=0.2, top_p=0.9)

    assert rest_calls[0]["generationConfig"] == {"temperature": 0.2, "topP": 0.9}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gemini-3.8-flash", {}),
        ("gemini-2.5-flash", {"temperature": 0.2, "top_p": 0.9}),
    ],
)
async def test_sdk_request_sampling_params_follow_the_model(model, expected):
    provider = _google_provider(model, base_url="https://generativelanguage.googleapis.com")
    if provider.model_instance is None:
        pytest.skip("google-generativeai is not installed")
    captured = {}

    async def fake_generate(prompt, generation_config, *args, **kwargs):
        captured.update(generation_config)
        raise RuntimeError("stop after the request is built")

    provider._generate_async = fake_generate
    with pytest.raises(Exception):
        await provider.text_completion("hello", temperature=0.2, top_p=0.9)

    assert captured == expected


def test_connection_test_payload_omits_temperature_for_gemini_3():
    payload = build_google_test_payload("Hi", "gemini-3.8-flash")

    assert payload["generationConfig"] == {}


def test_connection_test_payload_keeps_temperature_for_older_models():
    payload = build_google_test_payload("Hi", "gemini-2.5-flash")

    assert payload["generationConfig"] == {"temperature": 0}
