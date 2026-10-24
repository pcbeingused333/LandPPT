"""Real local html2canvas captures, including the hidden continuous editor iframe."""

import base64
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import STATIC, browser, ui_page  # noqa: F401
import test_antd_editor_ui as editor
from test_workspace_redesign_ui import workspace

OUT = Path("artifacts/vision-capture-20261024")
ARTWORK = '<html><body style="margin:0;width:1280px;height:720px"><main style="position:relative;width:1280px;height:720px;background:linear-gradient(120deg,#224466,#557799);color:white"><h1 style="margin:0;padding:40px;font:48px Arial">Visual capture</h1><div id="marker" style="position:absolute;left:180px;top:160px;width:280px;height:220px;background:#d72f3a"></div></main></body></html>'


def prepare(page, load, monkeypatch, html=ARTWORK):
    monkeypatch.setattr(editor, "HTML", html)
    state = workspace(page, load)
    expect(
        page.locator('.continuous-slide[data-slide-index="0"] iframe')
    ).to_be_visible()
    assert page.locator("#slideFrame").bounding_box() is None
    return state


def image_info(page, data):
    assert data.startswith("data:image/jpeg;base64,")
    return page.evaluate(
        """async data => {
        const image = new Image(); image.src = data; await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = image.width; canvas.height = image.height;
        const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
        const pixel = (x,y) => [...ctx.getImageData(x,y,1,1).data].slice(0,3);
        const pixels = ctx.getImageData(0,0,canvas.width,canvas.height).data;
        let min=255, max=0;
        for(let i=0;i<pixels.length;i+=4){min=Math.min(min,pixels[i]);max=Math.max(max,pixels[i]);}
        return {size:[image.width,image.height],variation:max-min,
          marker:pixel(220,220),svg:pixel(200,300),center:pixel(image.width/2,image.height/2)};
    }""",
        data,
    )


@pytest.mark.parametrize("mode", ["continuous", "preview", "edit", "split"])
def test_visual_mode_captures_current_artwork_in_all_editor_views(
    ui_page, monkeypatch, mode
):
    page, load = ui_page
    state = prepare(page, load, monkeypatch)
    original = page.evaluate("slidesData.map(slide=>slide.html_content)")
    if mode != "continuous":
        page.get_by_label("编辑视图").get_by_title(
            {"preview": "预览", "edit": "代码", "split": "分屏"}[mode], exact=True
        ).click()
    page.evaluate("window.originalLoad = document.getElementById('slideFrame').onload")
    page.get_by_role("button", name="视觉模式", exact=True).click()
    page.wait_for_function(
        "visionModeEnabled && !document.getElementById('aiVisionToggleBtn').disabled"
    )
    payload = page.evaluate("buildSidebarAgentPayload('检查布局', [])")
    assert payload["visionEnabled"] and payload["slideIndex"] == 1
    image = image_info(page, payload["slideScreenshot"])
    assert image["size"] == [1280, 720]
    assert image["variation"] > 10  # Painted content, not just a successful export.
    assert image["marker"] == pytest.approx((215, 47, 58), abs=4)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"capture-{mode}.jpg").write_bytes(
        base64.b64decode(payload["slideScreenshot"].split(",", 1)[1])
    )
    assert page.evaluate("slidesData.map(slide=>slide.html_content)") == original
    assert page.evaluate(
        "document.getElementById('slideFrame').onload === originalLoad"
    )
    assert (
        page.locator("iframe[data-slide-capture],script[src*='html2canvas']").count()
        == 0
    )
    assert not state["writes"] and not state["errors"]
    page.get_by_role("button", name="视觉模式", exact=True).click()
    assert page.evaluate("!visionModeEnabled")
    assert page.evaluate("captureSlideScreenshot()") is None


def test_capture_tracks_selected_page_and_preserves_svg(ui_page, monkeypatch):
    page, load = ui_page
    state = prepare(page, load, monkeypatch, html=editor.SVG_HTML)
    second = editor.SVG_HTML.replace("#dedede", "#3e8f73")
    page.evaluate(
        "html => {slidesData[1].html_content = html; selectSlide(1);}", second
    )
    page.wait_for_function("currentSlideIndex === 1")
    payload = page.evaluate(
        """async () => {
        await toggleVisionMode();
        return buildSidebarAgentPayload('检查 SVG', []);
    }"""
    )
    assert payload["slideIndex"] == 2
    image = image_info(page, payload["slideScreenshot"])
    assert image["size"] == [1280, 720]
    assert image["variation"] > 10
    assert image["svg"] == pytest.approx((62, 143, 115), abs=4)
    assert payload["slideContent"] == second
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("code_view", [False, True])
def test_library_failure_leaves_mode_off_and_can_retry(ui_page, monkeypatch, code_view):
    page, load = ui_page
    state = prepare(page, load, monkeypatch)
    if code_view:
        page.get_by_label("编辑视图").get_by_title("代码", exact=True).click()
    failed = [True]

    def library(route):
        if failed[0]:
            route.abort()
        else:
            route.fallback()

    page.route("**/vendor/html2canvas-1.4.1.min.js", library)
    page.evaluate("toggleVisionMode()")
    assert page.locator("iframe[data-slide-capture]").count() == 0
    assert page.evaluate(
        "!visionModeEnabled && !document.getElementById('aiVisionToggleBtn').disabled"
    )
    expect(
        page.get_by_text("视觉模式启用失败：截图组件加载失败，请重试", exact=True)
    ).to_have_count(1)
    failed[0] = False
    page.evaluate("toggleVisionMode()")
    assert page.evaluate("visionModeEnabled")
    assert page.locator("iframe[data-slide-capture]").count() == 0
    assert not state["writes"] and not state["errors"]


def test_page_change_during_capture_never_enables_stale_vision(ui_page, monkeypatch):
    page, load = ui_page
    prepare(page, load, monkeypatch)
    waiting = []
    page.route(
        "**/vendor/html2canvas-1.4.1.min.js", lambda route: waiting.append(route)
    )
    page.get_by_role("button", name="视觉模式", exact=True).click()
    expect(page.locator("#aiVisionToggleBtn")).to_be_disabled()
    page.wait_for_function(
        "!!document.querySelector('.continuous-slide iframe').contentDocument.querySelector('script[src*=html2canvas]')"
    )
    assert waiting
    page.evaluate("selectSlide(1)")
    for route in waiting:
        route.fulfill(
            body=(STATIC / "js/vendor/html2canvas-1.4.1.min.js").read_bytes(),
            content_type="text/javascript",
        )
    page.wait_for_function("!document.getElementById('aiVisionToggleBtn').disabled")
    assert page.evaluate("!visionModeEnabled")
    expect(
        page.get_by_text("视觉模式启用失败：页面已切换，请重新尝试截图", exact=True)
    ).to_be_visible()


def test_cross_origin_image_without_cors_does_not_taint_capture(ui_page, monkeypatch):
    page, load = ui_page
    png = page.evaluate(
        """() => {
        const canvas=document.createElement('canvas'); canvas.width=20;canvas.height=20;
        const ctx=canvas.getContext('2d');ctx.fillStyle='blue';ctx.fillRect(0,0,20,20);
        return canvas.toDataURL();
    }"""
    )
    body = base64.b64decode(png.split(",", 1)[1])
    page.route(
        "https://images.test/no-cors.png",
        lambda route: route.fulfill(body=body, content_type="image/png"),
    )
    html = ARTWORK.replace(
        "</main>",
        '<img src="https://images.test/no-cors.png" width="20" height="20"></main>',
    )
    state = prepare(page, load, monkeypatch, html=html)
    data = page.evaluate("captureSlideScreenshot({force:true})")
    image = image_info(page, data)
    assert image["size"] == [1280, 720] and image["variation"] > 10
    assert not state["writes"] and not state["errors"]


def test_quick_element_capture_uses_same_local_renderer(ui_page, monkeypatch):
    page, load = ui_page
    state = prepare(page, load, monkeypatch)
    page.get_by_role("button", name="快速编辑", exact=True).click()
    page.frame_locator("#slideFrame").locator("#marker").wait_for()
    data = page.evaluate(
        "captureQuickAiElementScreenshot(document.getElementById('slideFrame').contentDocument.getElementById('marker'))"
    )
    image = image_info(page, data)
    assert image["size"] == [280, 220]
    assert image["center"] == pytest.approx((215, 47, 58), abs=4)
    assert not state["writes"] and not state["errors"]


def test_failed_recapture_never_sends_text_only_as_visual(ui_page, monkeypatch):
    page, load = ui_page
    prepare(page, load, monkeypatch)
    result = page.evaluate(
        """async () => {
        await toggleVisionMode();
        withSlideCaptureFrame = async () => {throw new Error('capture failed')};
        try { await buildSidebarAgentPayload('检查布局', []); return 'sent'; }
        catch(error) { return error.message; }
    }"""
    )
    assert result == "当前页截图失败，请重试或关闭视觉模式后发送"
