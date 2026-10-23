"""Native Ant preview drawers and real browser media lifecycle, without AI."""

import io
import wave
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_artifact_library_ui import SIZES, files_tab, library_setup

OUT = Path("artifacts/artifact-preview-20261022")
VIDEO = (Path(__file__).parent / "fixtures/artifact-preview.webm").read_bytes()
audio = io.BytesIO()
with wave.open(audio, "wb") as sample:
    sample.setnchannels(1)
    sample.setsampwidth(2)
    sample.setframerate(8000)
    sample.writeframes(b"\0\0" * 8000 * 3)
AUDIO = audio.getvalue()


def preview_setup(page, load):
    state = library_setup(page, load)
    base = state["files"][0]
    state["files"][:] = [
        {
            **base,
            "id": "video",
            "filename": "很长的演示讲解文件名称" * 30 + ".webm",
            "category": "video",
            "category_label": "讲解视频",
            "preview_kind": "video",
        },
        {
            **base,
            "id": "audio",
            "filename": "讲解.wav",
            "category": "audio",
            "category_label": "讲解音频",
            "preview_kind": "audio",
        },
        {
            **base,
            "id": "zip",
            "filename": "讲解音频.zip",
            "category": "audio",
            "category_label": "讲解音频",
            "preview_kind": None,
        },
        {**base, "id": "pdf", "filename": "演示.pdf", "preview_kind": None},
        {
            **base,
            "id": "bad",
            "filename": '<img src=x onerror="window.previewInjected=true">.mp4',
            "preview_kind": "video",
        },
    ]
    state.update(media_reads=[], media_failed=False)

    def media_endpoint(route):
        state["media_reads"].append(route.request.url)
        if state["media_failed"]:
            route.fulfill(status=404, json={"detail": "文件已过期"})
            return
        is_audio = "/audio/" in route.request.url
        body = AUDIO if is_audio else VIDEO
        # Chromium sends an open-ended range for media. Honor it so the same
        # real decoder/control path is exercised instead of synthetic events.
        value = route.request.headers.get("range", "")
        start = int(value.removeprefix("bytes=").split("-")[0] or 0) if value else 0
        route.fulfill(
            status=206 if value else 200,
            body=body[start:],
            headers={
                "Content-Type": "audio/wav" if is_audio else "video/webm",
                "Accept-Ranges": "bytes",
                **(
                    {"Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}"}
                    if value
                    else {}
                ),
            },
        )

    page.route("**/api/artifact-library/*/preview", media_endpoint)
    region = files_tab(page)
    expect(page.get_by_text("共 5 个文件", exact=True)).to_be_visible()
    state["region"] = region
    return state


def open_preview(page, state, kind="video"):
    filename = next(file["filename"] for file in state["files"] if file["id"] == kind)
    trigger = state["region"].get_by_role("button", name="预览 " + filename, exact=True)
    trigger.click()
    dialog = page.get_by_role("dialog", name="音视频预览", exact=True)
    expect(dialog).to_be_visible()
    return dialog, trigger


@pytest.mark.parametrize("width,height", SIZES)
def test_preview_uses_native_drawer_controls_without_eager_media_loading(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    state = preview_setup(page, load)
    before = len(state["reads"])
    dialog, trigger = open_preview(page, state)
    player = dialog.locator("video")
    expect(player).to_have_attribute("controls", "")
    expect(player).to_have_attribute("preload", "none")
    expect(player).not_to_have_attribute("autoplay", "")
    expect(dialog.get_by_text("所属项目", exact=True)).to_be_visible()
    expect(dialog.get_by_role("link", name="下载文件", exact=True)).to_have_attribute(
        "href", "/api/artifacts/video/download"
    )
    assert not state["media_reads"] and len(state["reads"]) == before
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    bounds = player.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
    if width <= 390:
        assert bounds["y"] + bounds["height"] < height - 55
    OUT.mkdir(parents=True, exist_ok=True)
    page.mouse.move(1, height - 1)
    page.screenshot(
        path=str(OUT / f"preview-{width}x{height}.png"), animations="disabled"
    )
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()
    assert (
        not state["media_reads"]
        and not state["errors"]
        and not state["images"]["writes"]
    )


@pytest.mark.parametrize("kind", ["audio", "video"])
@pytest.mark.parametrize("closing", ["button", "escape"])
def test_real_playback_seek_and_close_release_media_without_writing(
    ui_page, kind, closing
):
    page, load = ui_page
    state = preview_setup(page, load)
    dialog, trigger = open_preview(page, state, kind)
    player = dialog.locator(kind)
    player.evaluate("e=>e.play()")
    expect(player).to_have_js_property("paused", False)
    assert player.evaluate("e=>e.duration") == pytest.approx(3, abs=0.01)
    player.evaluate("e=>e.currentTime=1.5")
    page.wait_for_function(
        "document.querySelector('.artifact-media-player video, .artifact-media-player audio').currentTime >= 1.5"
    )
    player.evaluate("e=>{window.closedPreview=e; e.pause()}")
    assert state["media_reads"]
    if closing == "button":
        dialog.locator(".ant-drawer-footer").get_by_role(
            "button", name="关闭", exact=True
        ).click()
    else:
        page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert page.evaluate(
        "window.closedPreview.paused && !window.closedPreview.getAttribute('src') && window.closedPreview.networkState===0"
    )
    expect(trigger).to_be_focused()
    assert (
        not state["errors"] and not state["images"]["writes"] and not state["downloads"]
    )


def test_expired_or_unsupported_media_can_retry_without_automatic_reloading(ui_page):
    page, load = ui_page
    state = preview_setup(page, load)
    state["media_failed"] = True
    dialog, _ = open_preview(page, state)
    dialog.locator("video").evaluate("e=>e.play().catch(()=>{})")
    expect(dialog.get_by_text("暂时无法播放", exact=True)).to_be_visible()
    expect(dialog.locator("video")).to_have_count(0)
    before = len(state["media_reads"])
    state["media_failed"] = False
    dialog.get_by_role("button", name="重试预览", exact=True).click()
    expect(dialog.locator("video")).to_have_count(1)
    assert len(state["media_reads"]) == before
    dialog.locator("video").evaluate("e=>e.play()")
    expect(dialog.locator("video")).to_have_js_property("paused", False)
    assert len(state["media_reads"]) > before
    assert not state["errors"] and not state["images"]["writes"]


def test_zip_and_pdf_remain_downloads_and_filename_is_never_rendered_as_html(ui_page):
    page, load = ui_page
    state = preview_setup(page, load)
    expect(
        state["region"].get_by_role("button", name="预览 讲解音频.zip", exact=True)
    ).to_have_count(0)
    expect(
        state["region"].get_by_role("button", name="预览 演示.pdf", exact=True)
    ).to_have_count(0)
    dialog, _ = open_preview(page, state, "bad")
    expect(
        dialog.get_by_text(state["files"][-1]["filename"], exact=True)
    ).to_be_visible()
    expect(dialog.locator("img,iframe,object,embed")).to_have_count(0)
    assert page.evaluate("!window.previewInjected")
    assert not state["media_reads"] and not state["images"]["writes"]


def test_preview_preserves_library_filters_and_unmounts_when_tab_changes(ui_page):
    page, load = ui_page
    state = preview_setup(page, load)
    search = page.get_by_role("searchbox", name="搜索导出文件", exact=True)
    search.fill("讲解.wav")
    expect(page.get_by_text("共 1 个文件", exact=True)).to_be_visible()
    dialog, _ = open_preview(page, state, "audio")
    player = dialog.locator("audio")
    player.evaluate("e=>{window.closedPreview=e; return e.play()}")
    # A parent navigation can change the active pane while a Drawer is open.
    page.get_by_role("tab", name="图片素材", exact=True).evaluate("e=>e.click()")
    expect(dialog).not_to_be_visible()
    assert page.evaluate(
        "window.closedPreview.paused && !window.closedPreview.getAttribute('src')"
    )
    files_tab(page)
    expect(search).to_have_value("讲解.wav")
    expect(page.get_by_text("共 1 个文件", exact=True)).to_be_visible()
    assert not state["images"]["writes"] and not state["errors"]
