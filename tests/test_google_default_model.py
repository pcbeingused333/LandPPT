from landppt.core.config import AIConfig


def test_google_model_default_is_a_served_model(monkeypatch):
    monkeypatch.delenv("GOOGLE_MODEL", raising=False)

    config = AIConfig(_env_file=None)

    assert config.google_model == "gemini-3.8-flash"
    assert config.get_provider_config("google")["model"] == "gemini-3.8-flash"
