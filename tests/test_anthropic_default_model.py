from landppt.core.config import AIConfig
from landppt.services.provider_test_utils import DEFAULT_ANTHROPIC_MODEL


def test_anthropic_model_default_is_a_served_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    config = AIConfig(_env_file=None)

    assert config.anthropic_model == "claude-haiku-4-5-20251001"
    assert config.get_provider_config("anthropic")["model"] == "claude-haiku-4-5-20251001"


def test_anthropic_connection_test_default_model():
    assert DEFAULT_ANTHROPIC_MODEL == "claude-sonnet-4-6"
