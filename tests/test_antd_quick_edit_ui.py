"""Quick editing chrome remains readable and preserves native element/AI actions."""

import re

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
import test_antd_editor_ui as editor

SIZES = [(1920, 1080), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
DARK_HTML = '<html><body style="margin:0;width:1280px;height:720px;background:#0b1118;color:#e8edf7;font-family:Arial"><h1 style="font-size:48px;margin:80px">原始演示内容</h1><p style="margin:80px">保留原始演示配色与尺寸。</p></body></html>'


def quick_editor(page, load, monkeypatch):
    monkeypatch.setattr(editor, "HTML", DARK_HTML)
    state = editor.setup(page, load)
    original = page.evaluate("slidesData[0].html_content")
    page.get_by_role("button", name="快速编辑", exact=True).click()
    heading = page.frame_locator("#slideFrame").locator("h1")
    expect(heading).to_have_class(re.compile("quick-edit-highlight"))
    heading.click()
    expect(page.locator("#boldBtn")).to_have_attribute("aria-pressed", "true")
    return state, original, heading


def styles(locator):
    return locator.evaluate(
        "e => {const s=getComputedStyle(e);return {color:s.color,background:s.backgroundColor}}"
    )


def contrast(colors):
    def luminance(color):
        channels = [int(value) / 255 for value in re.findall(r"\d+", color)[:3]]
        linear = [
            (
                channel / 12.92
                if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
            )
            for channel in channels
        ]
        return sum(
            value * weight for value, weight in zip(linear, [0.2126, 0.7152, 0.0722])
        )

    values = sorted([luminance(colors["color"]), luminance(colors["background"])])
    return (values[1] + 0.05) / (values[0] + 0.05)


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("scene", ["idle", "loading", "result"])
def test_quick_controls_and_ai_states_fit_and_keep_contrast(
    ui_page, monkeypatch, width, height, scene
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state, original, _ = quick_editor(page, load, monkeypatch)
    toolbar = page.get_by_role("toolbar", name="元素快速编辑", exact=True)
    expect(toolbar.locator(".editor-ant-native-icon svg")).to_have_count(16)
    box = toolbar.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
    primary_bar = page.locator("#editorAntToolbar").bounding_box()
    assert box["y"] >= primary_bar["y"] + primary_bar["height"]
    canvas = page.locator("#slideFrameWrapper").bounding_box()
    assert canvas["y"] >= box["y"] + box["height"]
    bold = page.locator("#boldBtn")
    bold.scroll_into_view_if_needed()
    bold.hover()
    expect(bold).to_have_css("background-color", "rgb(17, 17, 17)")
    expect(bold).to_have_css("color", "rgb(255, 255, 255)")
    assert contrast(styles(bold)) >= 4.5
    assert bold.bounding_box()["height"] >= (44 if width <= 700 else 32)
    page.locator("#quickAiEditToggleBtn").click()
    popup = page.get_by_role("dialog", name="AI雕琢", exact=True)
    expect(popup).to_be_visible()
    page.evaluate("() => setQuickAiVisionEnabledState(true,{persist:false})")
    if scene == "loading":
        page.evaluate(
            "() => {setQuickAiSendingState(true);setQuickAiStatus('AI 正在调整所选元素…')}"
        )
    elif scene == "result":
        page.evaluate(
            """() => {
            setQuickAiStatus('编辑完成（预览中，尚未保存）');
            setQuickAiResultBar([
                makeQuickAiResultButton('保留并保存','fa-check','primary',()=>{}),
                makeQuickAiResultButton('撤销','fa-undo','',()=>{}),
                makeQuickAiResultButton('看改动','fa-code','',()=>{})]);
            }"""
        )
    rect = popup.bounding_box()
    assert rect["x"] >= 0 and rect["x"] + rect["width"] <= width + 1
    assert rect["y"] >= 0 and rect["y"] + rect["height"] <= height + 1
    assert popup.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    vision = page.locator("#quickAiVisionToggleBtn")
    vision.hover()
    expect(vision).to_have_css("background-color", "rgb(17, 17, 17)")
    expect(vision).to_have_css("color", "rgb(255, 255, 255)")
    assert contrast(styles(vision)) >= 4.5
    if scene != "loading":
        apply = popup.get_by_role("button", name="应用", exact=True)
        apply.hover()
        expect(apply).to_have_css("background-color", "rgb(17, 17, 17)")
        expect(apply).to_have_css("color", "rgb(255, 255, 255)")
        assert contrast(styles(apply)) >= 4.5
    for button in popup.get_by_role("button").all():
        button.scroll_into_view_if_needed()
        assert button.bounding_box()["height"] >= (44 if width <= 700 else 32)
    assert page.evaluate("slidesData[0].html_content") == original
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("width", [1440, 320])
def test_ai_restored_size_fills_input_and_minimize_restores_draft(
    ui_page, monkeypatch, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=844))
    state, _, _ = quick_editor(page, load, monkeypatch)
    page.evaluate(
        "localStorage.setItem('quickAiPopoverSize',JSON.stringify({width:540,height:360}))"
    )
    page.locator("#quickAiEditToggleBtn").click()
    popup = page.get_by_role("dialog", name="AI雕琢", exact=True)
    field = popup.get_by_role("textbox", name="修改要求", exact=True)
    field.fill("让这段文字更简洁")
    assert field.bounding_box()["height"] > 140
    assert popup.bounding_box()["height"] <= 361
    popup.get_by_role("button", name="最小化", exact=True).click()
    expect(field).not_to_be_visible()
    assert popup.bounding_box()["height"] <= (64 if width <= 700 else 52)
    restore = popup.get_by_role("button", name="还原", exact=True)
    assert restore.bounding_box()["height"] >= (44 if width <= 700 else 32)
    restore.click()
    expect(field).to_have_value("让这段文字更简洁")
    assert field.bounding_box()["height"] > 140
    field.press("Shift+Enter")
    expect(field).to_have_value("让这段文字更简洁\n")
    field.press("Escape")
    expect(popup).not_to_be_visible()
    page.locator("#quickAiEditToggleBtn").click()
    expect(field).to_have_value("让这段文字更简洁\n")
    assert not state["errors"] and not state["writes"]


def test_quick_format_toggles_remain_native_and_keep_slide_colors(ui_page, monkeypatch):
    page, load = ui_page
    state, _, heading = quick_editor(page, load, monkeypatch)
    for identifier, property_name, expected in [
        ("boldBtn", "fontWeight", "400"),
        ("italicBtn", "fontStyle", "italic"),
        ("underlineBtn", "textDecorationLine", "underline"),
    ]:
        page.locator("#" + identifier).click()
        assert (
            heading.evaluate("(e,p) => getComputedStyle(e)[p]", property_name)
            == expected
        )
    assert heading.evaluate("e => getComputedStyle(e).color") == "rgb(232, 237, 247)"
    assert (
        page.frame_locator("#slideFrame")
        .locator("body")
        .evaluate("e => getComputedStyle(e).backgroundColor")
        == "rgb(11, 17, 24)"
    )
    assert not state["errors"]


@pytest.mark.parametrize("width", [1440, 320])
def test_small_saved_popover_keeps_apply_fully_visible(ui_page, monkeypatch, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=844))
    state, _, _ = quick_editor(page, load, monkeypatch)
    page.evaluate(
        "localStorage.setItem('quickAiPopoverSize',JSON.stringify({width:280,height:206}))"
    )
    page.locator("#quickAiEditToggleBtn").click()
    popup = page.get_by_role("dialog", name="AI雕琢", exact=True)
    body = popup.locator(".quick-ai-edit-popover-body")
    page.wait_for_function(
        "document.querySelector('.quick-ai-edit-popover-body').scrollHeight <= document.querySelector('.quick-ai-edit-popover-body').clientHeight + 1"
    )
    apply = popup.get_by_role("button", name="应用", exact=True)
    box, bounds = apply.bounding_box(), body.bounding_box()
    assert box["y"] + box["height"] <= bounds["y"] + bounds["height"] + 1
    assert apply.evaluate(
        "e => {const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.bottom-2))}"
    )
    assert not state["errors"] and not state["writes"]


def test_ai_enter_request_failure_keeps_draft_and_supports_retry(ui_page, monkeypatch):
    page, load = ui_page
    state, original, _ = quick_editor(page, load, monkeypatch)
    page.locator("#quickAiEditToggleBtn").click()
    page.evaluate(
        """() => {
          window.quickRequests=[];window.quickReverts=0;
          window.landpptAgentClient={
            beginPreviewSession:()=>({push(){},release(){},revert(){quickReverts++}}),
            start:({payload})=>{
              quickRequests.push(payload);
              return {done:new Promise((resolve,reject)=>window.rejectQuick=()=>reject(new Error('服务暂时不可用'))),cancel(){}};
            }
          };
        }"""
    )
    popup = page.get_by_role("dialog", name="AI雕琢", exact=True)
    field = popup.get_by_role("textbox", name="修改要求", exact=True)
    field.fill("简化选中的标题")
    field.press("Enter")
    expect(field).to_be_disabled()
    expect(popup.get_by_role("button", name="应用", exact=True)).to_be_disabled()
    expect(popup.get_by_role("button", name="停止", exact=True)).to_be_visible()
    page.evaluate("rejectQuick()")
    expect(popup.locator("#quickAiEditStatus")).to_have_text("失败：服务暂时不可用")
    expect(field).to_have_value("简化选中的标题")
    expect(field).to_be_enabled()
    popup.get_by_role("button", name="应用", exact=True).click()
    expect(popup.get_by_role("button", name="停止", exact=True)).to_be_visible()
    page.evaluate("rejectQuick()")
    expect(field).to_be_enabled()
    requests = page.evaluate("quickRequests")
    assert len(requests) == 2 and all(
        request["mode"] == "element"
        and request["slideIndex"] == 1
        and request["userRequest"] == "简化选中的标题"
        and request["visionEnabled"] is False
        for request in requests
    )
    assert page.evaluate("quickReverts") == 2
    assert page.evaluate("slidesData[0].html_content") == original
    assert not state["errors"] and not state["writes"]
