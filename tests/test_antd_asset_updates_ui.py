"""Browser cache must not keep an older UI after the next document navigation."""

import json
import mimetypes
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import (
    ROOT,
    STATIC,
    browser,
    template_environment,
    ui_page,
)  # noqa: F401

BASE = (ROOT / "src/landppt/web/templates/antd_base.html").read_text(encoding="utf-8")
LOADER = re.search(r'<script type="module" src="([^"]+/antd/app.js[^"]*)"', BASE)[1]
STYLESHEET = re.search(r'href="([^"]+/antd/app.css[^"]*)"', BASE)[1]
MANIFEST = "/static/antd/manifest.json?" + urlsplit(LOADER).query


@contextmanager
def cached_ui_server(previous_loader=False, previous_assets=None):
    """Real HTTP responses: Playwright route interception disables HTTP cache."""
    state = {"updated": False, "requests": []}
    env = template_environment(ROOT / "src/landppt/web/templates")
    user = dict(username="ui-test", is_admin=True)
    html = env.get_template("pages/settings/ai_config.html").render(
        user=user,
        request=SimpleNamespace(state=SimpleNamespace(user=user)),
        current_config=dict(
            enable_image_service=True,
            enable_ai_generation=True,
            default_ai_image_provider="openai_image",
        ),
        current_provider="openai",
        provider_status={},
    )
    old_entry = b"document.querySelector('#antdRoot').innerHTML='<p>Old interface</p>';"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append(self.path)
            path = unquote(urlsplit(self.path).path)
            status, cache, mime = 200, "no-store", "application/json"
            if path == "/old":
                body = (
                    '<div id="antdRoot"></div><script type="module" src="'
                    + (LOADER if previous_loader else "/static/antd/app.js")
                    + '"></script>'
                ).encode()
                if previous_assets is not None:
                    body = (
                        html.replace(LOADER, "/static/antd/app.js")
                        .replace(
                            STYLESHEET,
                            "/static/antd/app.css?v=previous-build",
                        )
                        .encode()
                    )
                mime = "text/html; charset=utf-8"
            elif path == "/ai-config":
                body, mime = html.encode(), "text/html; charset=utf-8"
            elif path.startswith("/static/"):
                # Aggressive intermediary/browser caching models the old entry
                # and a stale manifest, while still serving the current build.
                cache = "public, max-age=31536000"
                previous = (
                    previous_assets / path.removeprefix("/static/")
                    if previous_assets is not None
                    else None
                )
                if (
                    not state["updated"]
                    and previous is not None
                    and previous.resolve().is_relative_to(previous_assets.resolve())
                    and previous.is_file()
                ):
                    body = previous.read_bytes()
                    mime = (
                        mimetypes.guess_type(str(previous))[0]
                        or "application/octet-stream"
                    )
                elif path == "/static/antd/app-old-build.js":
                    body, mime = old_entry, "application/javascript"
                elif (
                    path == "/static/antd/app.js"
                    and not state["updated"]
                    and not previous_loader
                ):
                    body, mime = old_entry, "application/javascript"
                elif path == "/static/antd/manifest.json" and not state["updated"]:
                    body = json.dumps(
                        {"src/main.tsx": {"file": "app-old-build.js"}}
                    ).encode()
                else:
                    source = STATIC / path.removeprefix("/static/")
                    if (
                        source.resolve().is_relative_to(STATIC.resolve())
                        and source.is_file()
                    ):
                        body = source.read_bytes()
                        mime = (
                            mimetypes.guess_type(str(source))[0]
                            or "application/octet-stream"
                        )
                    else:
                        status, body = 404, b""
            else:
                body = json.dumps(
                    dict(
                        success=True,
                        config={},
                        data=[],
                        enabled=False,
                        status="ok",
                        available_providers=["openai_image"],
                    )
                ).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class AssetServer(ThreadingHTTPServer):
        # ES modules request many files at once. The default five-connection
        # listen queue is smaller than a real ASGI server's backlog.
        request_queue_size = 64

    server = AssetServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("previous_loader", [False, True])
def test_cached_entry_and_manifest_do_not_keep_old_configuration_ui(
    browser, width, previous_loader
):
    with cached_ui_server(previous_loader) as (origin, state):
        context = browser.new_context(viewport=dict(width=width, height=900))
        page = context.new_page()
        errors = []
        failed_requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                (urlsplit(request.url).path, request.failure)
            ),
        )
        page.goto(origin + "/old", wait_until="networkidle")
        expect(page.get_by_text("Old interface", exact=True)).to_be_visible()
        if not previous_loader:
            page.evaluate("url => fetch(url)", MANIFEST)
        state["updated"] = True
        # Ordinary navigation, no forced reload, cache clearing or route mocks.
        page.goto(origin + "/ai-config", wait_until="networkidle")
        tab = page.get_by_role("tab", name="图片服务", exact=True)
        expect(
            tab,
            str(
                dict(
                    errors=errors,
                    failed_requests=failed_requests,
                    requests=state["requests"],
                )
            ),
        ).to_be_visible()
        tab.click()
        expect(page.locator(".image-settings-grid")).to_be_visible()
        expect(page.locator("#image-service .config-section-card")).to_have_count(3)
        expect(page.locator("#field-openai_image_model")).to_be_visible()
        assert (
            page.locator("#image-service")
            .get_by_text("详细配置 · 本地图床配置", exact=True)
            .count()
            == 0
        )
        page.locator("#field-max_ai_images_per_slide").fill("2")
        page.locator("#field-enable_ai_generation").click()
        expect(page.locator("#field-max_ai_images_per_slide")).to_have_count(0)
        page.locator("#field-enable_ai_generation").click()
        expect(page.locator("#field-max_ai_images_per_slide")).to_have_value("2")
        manifest = json.loads((STATIC / "antd/manifest.json").read_text())
        root = "/static/antd/" + manifest["src/main.tsx"]["file"]
        assert state["requests"].count(root) == 1
        assert state["requests"].count("/api/config/all") == 1
        assert state["requests"].count(MANIFEST) == 2
        if previous_loader:
            assert state["requests"].count(LOADER) == 1  # loader itself is cached
        else:
            assert state["requests"].count("/static/antd/app.js") == 1
            assert state["requests"].count(LOADER) == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors
        context.close()


@pytest.mark.parametrize("failure", ["unavailable", "invalid", "missing-entry"])
def test_ui_discovery_failure_has_accessible_retry_and_never_uses_old_entry(
    ui_page, failure
):
    page, load = ui_page
    state = {"failed": True}

    def manifest(route):
        if not state["failed"]:
            route.fallback()
        elif failure == "unavailable":
            route.fulfill(status=503, body="unavailable")
        else:
            route.fulfill(
                json={
                    "src/main.tsx": {
                        "file": (
                            "https://invalid.example/app.js"
                            if failure == "invalid"
                            else "app-missing.js"
                        )
                    }
                }
            )

    page.route("**/static/antd/manifest.json**", manifest)
    load("pages/settings/ai_config.html", path="/ai-config")
    expect(page.get_by_role("alert")).to_have_text(
        "界面资源加载失败，请刷新页面后重试。"
    )
    assert page.locator(".configuration-page").count() == 0
    state["failed"] = False
    retry = page.get_by_role("button", name="刷新页面", exact=True)
    retry.focus()
    retry.press("Enter")
    page.get_by_role("heading", name="系统配置管理", exact=True).wait_for()
    page.get_by_role("tab", name="图片服务", exact=True).click()
    expect(page.locator(".image-credentials-collapse")).to_be_visible()
