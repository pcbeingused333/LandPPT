"""Inspect each painted frame while the speech dialog adapter is delayed."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import SCRIPTS, setup
from test_antd_editor_documents_ui import document_setup, panel


def delay_dialog_adapter(page):
    page.add_init_script(
        """(() => {
      let bridge;
      Object.defineProperty(window, 'LandPPTEditorSurfaces', {
        configurable: true,
        get: () => bridge,
        set(value) {
          bridge = value;
          const subscribe = bridge.subscribe;
          bridge.subscribe = listener => subscribe(state => {
            if (state.dialogs.some(record => !record.node.querySelector('.ant-modal-root'))) {
              setTimeout(() => listener(bridge.read()), window.speechDialogTestDelay || 250);
            } else listener(state);
          });
        },
      });
    })();"""
    )


def trace_speech_frames(page):
    page.evaluate(
        """() => {
      window.speechPaints = [];
      window.speechTraceActive = true;
      const visible = node => {
        if (!node || !node.getClientRects().length) return false;
        for (let parent = node; parent; parent = parent.parentElement) {
          const style = getComputedStyle(parent);
          if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
        }
        return true;
      };
      const sample = () => {
        speechPaints.push({
          legacy: Array.from(document.querySelectorAll('body > .modal > .speech-modal-dialog')).some(visible),
          modern: visible(document.querySelector('.editor-ant-dialog .ant-modal-container')),
        });
        if (speechTraceActive) requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    }"""
    )


def stop_speech_trace(page):
    return page.evaluate("() => {speechTraceActive=false;return speechPaints}")


@pytest.mark.parametrize("size", [(1440, 900), (390, 844), (320, 568), (844, 390)])
def test_view_all_speech_never_paints_old_dialog_even_when_adapter_is_delayed(
    ui_page, size
):
    page, load = ui_page
    page.set_viewport_size(dict(zip(("width", "height"), size)))
    delay_dialog_adapter(page)
    state = document_setup(page, load)
    panel(page, "讲稿")
    expect(page.get_by_role("button", name="查看全部", exact=True)).to_be_visible()
    for _ in range(2):
        trace_speech_frames(page)
        page.get_by_role("button", name="查看全部", exact=True).click()
        dialog = page.locator(".editor-ant-dialog")
        expect(dialog).to_be_visible()
        expect(dialog.locator(".speech-script-content")).to_be_visible()
        expect(dialog.get_by_role("textbox", name="演讲稿内容")).to_have_count(0)
        page.wait_for_function("speechPaints.some(sample=>sample.modern)")
        frames = stop_speech_trace(page)
        assert not any(frame["legacy"] for frame in frames), frames
        assert any(frame["modern"] for frame in frames)
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(page.locator("body > .modal")).to_have_count(0)
        expect(page.get_by_role("button", name="查看全部", exact=True)).to_be_focused()
    assert not state["writes"] and not state["document_writes"] and not state["errors"]


def test_generation_settings_share_the_staged_handoff(ui_page):
    page, load = ui_page
    delay_dialog_adapter(page)
    state = setup(page, load)
    trace_speech_frames(page)
    page.evaluate("showSpeechScriptDialog()")
    dialog = page.locator(".editor-ant-dialog")
    expect(dialog).to_be_visible()
    page.wait_for_function("speechPaints.some(sample=>sample.modern)")
    assert not any(frame["legacy"] for frame in stop_speech_trace(page))
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert not state["writes"] and not state["errors"]


def test_native_speech_preview_remains_available_without_react_adapter(ui_page):
    page, load = ui_page
    page.route("**/static/antd/app.js?*", lambda route: route.abort())
    state = setup(page, load, native=True)
    page.evaluate("result=>showSpeechScriptPreview(result,false)", SCRIPTS)
    expect(page.locator("body > .modal > .speech-modal-dialog")).to_be_visible()
    assert page.locator(".editor-ant-dialog").count() == 0
    page.locator(".speech-modal-close").click()
    expect(page.locator("body > .modal")).to_have_count(0)
    assert not state["writes"] and not state["errors"]
