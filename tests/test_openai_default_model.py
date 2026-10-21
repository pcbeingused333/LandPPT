from landppt.core.config import AIConfig
from landppt.services.provider_test_utils import DEFAULT_OPENAI_MODEL


def test_openai_model_default_is_not_gpt_3_5(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = AIConfig(_env_file=None)

    assert config.openai_model == "gpt-4.1"
    assert config.get_provider_config("openai")["model"] == "gpt-4.1"


def test_openai_connection_test_default_model():
    assert DEFAULT_OPENAI_MODEL == "gpt-4.1"
