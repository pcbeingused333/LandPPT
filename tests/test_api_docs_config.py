def _reload_main_module(monkeypatch, enabled: bool, load_isolated_module):
    from landppt.core.config import app_config

    monkeypatch.setattr(app_config, "enable_api_docs", enabled)
    return load_isolated_module("landppt.main")


def test_main_app_enables_api_docs_by_default(monkeypatch, load_isolated_module):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    module = _reload_main_module(monkeypatch, True, load_isolated_module)

    assert module.app.docs_url == "/docs"
    assert module.app.redoc_url == "/redoc"
    assert module.app.openapi_url == "/openapi.json"


def test_main_app_can_disable_api_docs(monkeypatch, load_isolated_module):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")

    module = _reload_main_module(monkeypatch, False, load_isolated_module)

    assert module.app.docs_url is None
    assert module.app.redoc_url is None
    assert module.app.openapi_url is None
