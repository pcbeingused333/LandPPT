import logging

from landppt.services.config_service import ConfigService
from landppt.services.image.config.image_config import image_config


def test_reload_image_config_applies_saved_settings_without_error(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    service = ConfigService(str(tmp_path / ".env"))
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "new-key")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "new-model")
    monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "high")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "new-gemini-model")

    with caplog.at_level(logging.ERROR):
        service._reload_image_config()

    assert image_config._config["openai_image"]["api_key"] == "new-key"
    assert image_config._config["openai_image"]["model"] == "new-model"
    assert image_config._config["openai_image"]["default_quality"] == "high"
    assert image_config._config["gemini"]["model"] == "new-gemini-model"
    assert [r.message for r in caplog.records if r.levelno >= logging.ERROR] == []
