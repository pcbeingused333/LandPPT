import pytest

from landppt.ai.providers import OpenAIProvider

REASONING_MODELS = [
    "gpt-5",
    "gpt-5-mini",
    "gpt-5.1",
    "gpt-5.6-sol",
    "gpt-6-luna",
    "gpt-6-astra",
    "o1",
    "o1-preview",
    "o3-mini",
    "o4-mini",
    "openai/gpt-5",
]
SAMPLING_MODELS = [
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-5-chat-latest",
    "gpt-6-chat-latest",
    "gpt-3.5-turbo",
    "omni-moderation-latest",
    "deepseek-chat",
]


def _provider(model):
    return OpenAIProvider({"api_key": "test-key", "model": model})


def _chat_request(model):
    return _provider(model)._build_chat_completions_request(
        {"model": model}, [{"role": "user", "content": "hi"}]
    )


def _responses_request(model):
    return _provider(model)._build_responses_request(
        {"model": model}, [{"role": "user", "content": "hi"}]
    )


@pytest.mark.parametrize("build", [_chat_request, _responses_request])
@pytest.mark.parametrize("model", REASONING_MODELS)
def test_sampling_fields_are_omitted_for_reasoning_models(build, model):
    request = build(model)

    assert "temperature" not in request
    assert "top_p" not in request


@pytest.mark.parametrize("build", [_chat_request, _responses_request])
@pytest.mark.parametrize("model", SAMPLING_MODELS)
def test_sampling_fields_are_kept_for_other_models(build, model):
    request = build(model)

    assert request["temperature"] == 0.7
    assert request["top_p"] == 1.0
