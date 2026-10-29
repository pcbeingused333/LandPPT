import pytest

from landppt.ai.providers import OpenAIProvider

REASONING_MODELS = [
    "gpt-5",
    "gpt-5-mini",
    "gpt-5.2",
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


NONE_EFFORT_MODELS = ["gpt-5.1", "gpt-5.6-sol", "gpt-6-luna", "gpt-6-sol", "gpt-6.1-terra", "openai/gpt-5.6-terra"]
NO_NONE_EFFORT_MODELS = [
    "gpt-5",
    "gpt-5-mini",
    "o3-mini",
    "gpt-5.1-codex",
    "gpt-5.2-pro",
    "gpt-6-astra",
    "openai/gpt-6-astra",
    "gpt-6.1-sol",
]
SAMPLING_CONFIG = {"temperature": 0.2, "top_p": 0.6}


def _chat_with(model, extra):
    return _provider(model)._build_chat_completions_request(
        {"model": model, **SAMPLING_CONFIG, **extra}, [{"role": "user", "content": "hi"}]
    )


def _responses_with(model, extra):
    return _provider(model)._build_responses_request(
        {"model": model, **SAMPLING_CONFIG, **extra}, [{"role": "user", "content": "hi"}]
    )


@pytest.mark.parametrize("build", [_chat_with, _responses_with])
@pytest.mark.parametrize("model", NONE_EFFORT_MODELS)
def test_sampling_fields_are_kept_when_reasoning_effort_is_none(build, model):
    request = build(model, {"enable_reasoning": True, "reasoning_effort": "none"})

    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.6


@pytest.mark.parametrize("build", [_chat_with, _responses_with])
@pytest.mark.parametrize("model", NONE_EFFORT_MODELS)
def test_sampling_fields_are_omitted_for_a_non_none_effort(build, model):
    request = build(model, {"enable_reasoning": True, "reasoning_effort": "medium"})

    assert "temperature" not in request
    assert "top_p" not in request


@pytest.mark.parametrize("build", [_chat_with, _responses_with])
@pytest.mark.parametrize("model", [m for m in NONE_EFFORT_MODELS if m != "gpt-5.1"])
@pytest.mark.parametrize("extra", [{}, {"enable_reasoning": False, "reasoning_effort": "none"}])
def test_sampling_fields_are_omitted_when_no_effort_is_sent(build, model, extra):
    request = build(model, extra)

    assert "temperature" not in request
    assert "top_p" not in request


@pytest.mark.parametrize("build", [_chat_with, _responses_with])
@pytest.mark.parametrize("model", NO_NONE_EFFORT_MODELS)
def test_sampling_fields_stay_omitted_when_model_has_no_none_effort(build, model):
    request = build(model, {"enable_reasoning": True, "reasoning_effort": "none"})

    assert "temperature" not in request
    assert "top_p" not in request


@pytest.mark.parametrize("build", [_chat_with, _responses_with])
@pytest.mark.parametrize("extra", [{}, {"enable_reasoning": False}])
@pytest.mark.parametrize("model", ["gpt-5.1", "gpt-5.1-2025-11-13"])
def test_sampling_fields_are_kept_without_effort_when_the_model_defaults_to_none(build, model, extra):
    request = build(model, extra)

    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.6


@pytest.mark.parametrize("build", [_chat_with, _responses_with])
@pytest.mark.parametrize("model", ["gpt-5.6-sol", "gpt-6-luna", "gpt-5", "gpt-5.1-codex"])
def test_sampling_fields_are_omitted_without_effort_when_the_model_does_not_default_to_none(build, model):
    request = build(model, {})

    assert "temperature" not in request
    assert "top_p" not in request
