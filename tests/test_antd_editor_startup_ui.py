"""Hold real startup assets to check intermediate paints, not just final layout."""

import base64
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import STATIC, browser, ui_page  # noqa: F401
from test_workspace_redesign_ui import workspace

OUT = Path("artifacts/editor-startup-20261024")


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
@pytest.mark.parametrize("stage", ["engine", "workspace"])
def test_editor_stages_native_nodes_until_workspace_is_ready(
    ui_page, monkeypatch, width, height, stage
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script(
        """(() => {
        window.editorStartupFrames = {staged: 0, ready: 0, misplaced: 0};
        const inspect = () => {
            const rail = document.getElementById('slidesSidebar');
            const editor = document.querySelector('.editor-container');
            if (rail && editor) {
                const style = getComputedStyle(rail), rect = rail.getBoundingClientRect();
                const shown = style.visibility === 'visible' && rect.width > 0 && rect.height > 0;
                if (editor.hasAttribute('data-editor-staged')) window.editorStartupFrames.staged++;
                else window.editorStartupFrames.ready++;
                if (shown && (!rail.closest('.workspace-files-host') ||
                    !editor.closest('.workspace-native-root') ||
                    !document.querySelector('.editor-ant-toolbar'))) window.editorStartupFrames.misplaced++;
            }
            requestAnimationFrame(inspect);
        };
        requestAnimationFrame(inspect);
        })();"""
    )
    manifest = json.loads((STATIC / "antd/manifest.json").read_text(encoding="utf-8"))
    asset = (
        STATIC / "js/pages/project/slides_editor/projectSlidesEditor.core.js"
        if stage == "engine"
        else STATIC / "antd" / manifest["src/pages/slides-editor.tsx"]["file"]
    )
    held = []
    requested = []
    page.on("request", lambda req: requested.append(req.url))
    page.route("**/" + asset.name + "*", lambda route: held.append(route))
    original_goto = page.goto

    def delayed_load(*args, **kwargs):
        # Return as soon as parsing starts; the real fixture otherwise waits for
        # networkidle, which would hide the very startup phase under test.
        with monkeypatch.context() as patch:
            patch.setattr(
                page, "goto", lambda url, **_: original_goto(url, wait_until="commit")
            )
            load(*args, **kwargs)
        expect(page.get_by_role("status", name="正在打开编辑器")).to_be_visible()
        expect(page.locator(".editor-container")).to_have_css("visibility", "hidden")
        expect(page.locator("#slidesSidebar")).to_be_hidden()
        expect(page.locator("body > .editor-container")).to_have_css(
            "position", "fixed"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.wait_for_function("window.editorStartupFrames.staged > 1")
        if stage == "engine":
            # Parsing and later downloads can proceed while the core is held.
            expect(page.locator("#antdData")).to_be_attached()
            assert any("projectSlidesEditor.engine.js" in url for url in requested)
        else:
            expect(
                page.locator(".app-sidebar" if width >= 1024 else ".app-header")
            ).to_be_visible()
        OUT.mkdir(parents=True, exist_ok=True)
        # Font readiness waits for DOMContentLoaded, deliberately blocked by
        # the held engine. Capture the current painted viewport directly.
        session = page.context.new_cdp_session(page)
        capture = session.send("Page.captureScreenshot", {"format": "png"})
        session.detach()
        (OUT / f"pending-{stage}-{width}.png").write_bytes(
            base64.b64decode(capture["data"])
        )
        assert held
        for route in held:
            route.fulfill(body=asset.read_bytes(), content_type="text/javascript")
        expect(page.locator(".editor-mount")).to_have_attribute("aria-busy", "false")
        expect(page.get_by_role("status", name="正在打开编辑器")).to_have_count(0)
        expect(page.get_by_role("region", name="连续幻灯片预览")).to_be_visible()
        assert page.locator("body > .editor-container").count() == 0
        page.wait_for_function("window.editorStartupFrames.ready > 1")
        assert page.evaluate("window.editorStartupFrames.misplaced") == 0
        assert page.locator(".workspace-preview-host").bounding_box()["width"] > 100
        assert page.locator(".continuous-preview iframe").first.get_attribute("srcdoc")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUT / f"ready-{stage}-{width}.png"))
        return page

    state = workspace(page, delayed_load)
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("asset_key", ["src/main.tsx", "src/pages/slides-editor.tsx"])
def test_editor_asset_failure_offers_retry_without_showing_staged_nodes(
    ui_page, asset_key
):
    page, load = ui_page
    manifest = json.loads((STATIC / "antd/manifest.json").read_text(encoding="utf-8"))
    page.route("**/" + manifest[asset_key]["file"], lambda route: route.abort())

    def failed_load(*args, **kwargs):
        load(*args, **kwargs)
        expect(page.get_by_role("button", name="刷新页面", exact=True)).to_be_visible()
        expect(page.get_by_role("status", name="正在打开编辑器")).to_have_count(0)
        expect(page.locator(".editor-container")).to_have_css("visibility", "hidden")
        expect(page.locator("#slidesSidebar")).to_be_hidden()
        return page

    # This scenario intentionally never mounts the toolbar. The underlying
    # fixture's native mode exposes it only after failed_load checks the gate.
    from test_antd_editor_ui import setup

    setup(page, failed_load, native=True)
