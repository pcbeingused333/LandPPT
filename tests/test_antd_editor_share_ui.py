"""Share dialog controls retain the native link, clipboard and request handlers."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import setup

SIZES = [(1920, 1080), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
TOKEN = "demonstration-token-" * 8
SHARE_URL = "http://ui.test/share/" + TOKEN
NARRATION_URL = SHARE_URL + "?narration=1&language=en"


def open_share(page, load, narration=True):
    state = setup(page, load)
    page.route(
        "**/share/generate",
        lambda route: route.fulfill(json={"share_url": "/share/" + TOKEN}),
    )
    page.evaluate(
        """enabled => {
            window.landpptEditorConfig.hasSpeechScripts = enabled;
            window.landpptEditorConfig.narrationLanguages = ['en', 'zh'];
            window.sharedCopies = []; window.sharedOpens = [];
            Object.defineProperty(navigator, 'clipboard', {configurable: true,
                value: {writeText: url => {sharedCopies.push(url); return Promise.resolve();}}});
            window.open = (url, target) => {sharedOpens.push([url, target]); return null;};
        }""",
        narration,
    )
    trigger = page.get_by_role("button", name="更多工具", exact=True)
    trigger.click()
    page.get_by_role("menuitem", name="分享链接", exact=True).click()
    dialog = page.get_by_role("dialog", name="分享链接", exact=True)
    expect(dialog).to_be_visible()
    return state, dialog, trigger


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("narration", [False, True])
def test_share_links_fit_and_copy_without_restyling_slides(
    ui_page, width, height, narration
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state, dialog, trigger = open_share(page, load, narration)
    artwork = page.locator("#slideFrame").get_attribute("srcdoc")
    box = dialog.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
    assert dialog.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    expect(page.locator(".lp-share-modal > .lp-share-modal-dialog")).to_be_hidden()
    expect(dialog.get_by_role("textbox", name="演示链接", exact=True)).to_have_value(
        SHARE_URL
    )
    expect(dialog.get_by_role("textbox", name="讲解链接", exact=True)).to_have_count(
        int(narration)
    )
    if narration:
        expect(
            dialog.get_by_role("textbox", name="讲解链接", exact=True)
        ).to_have_value(NARRATION_URL)
    for button in dialog.get_by_role("button").all():
        button.scroll_into_view_if_needed()
        rect = button.bounding_box()
        assert rect["height"] >= (44 if width <= 700 else 32)
        assert rect["x"] >= 0 and rect["x"] + rect["width"] <= width + 1
        assert button.evaluate(
            """e => {const r=e.getBoundingClientRect();
            return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}"""
        )
    footer = dialog.locator(".ant-modal-footer").bounding_box()
    assert footer["y"] + footer["height"] <= height + 1
    dialog.get_by_role("button", name="复制链接", exact=True).click()
    if narration:
        dialog.get_by_role("button", name="复制讲解链接", exact=True).click()
    assert page.evaluate("sharedCopies") == [SHARE_URL] + (
        [NARRATION_URL] if narration else []
    )
    dialog.get_by_role("button", name="打开演示", exact=True).click()
    if narration:
        dialog.get_by_role("button", name="打开讲解", exact=True).click()
    assert page.evaluate("sharedOpens") == [[SHARE_URL, "_blank"]] + (
        [[NARRATION_URL, "_blank"]] if narration else []
    )
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()
    assert page.locator("#slideFrame").get_attribute("srcdoc") == artwork
    assert not state["errors"] and not state["writes"]


def test_share_disable_failure_retains_links_and_success_closes(ui_page):
    page, load = ui_page
    state, dialog, trigger = open_share(page, load)
    requests = []

    def disable(route):
        requests.append((route.request.method, route.request.post_data))
        if len(requests) == 1:
            route.fulfill(status=503, json={"detail": "暂时不可用"})
        else:
            route.fulfill(json={"success": True})

    page.route("**/share/disable", disable)
    dialog.get_by_role("button", name="禁用分享", exact=True).click()
    expect(page.get_by_text("禁用分享失败: 禁用分享失败", exact=True)).to_be_visible()
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("textbox", name="演示链接", exact=True)).to_have_value(
        SHARE_URL
    )
    dialog.get_by_role("button", name="禁用分享", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()
    assert requests == [("POST", None), ("POST", None)]
    assert not state["errors"]


def test_share_clipboard_fallback_and_keyboard_tooltip(ui_page):
    page, load = ui_page
    state, dialog, _ = open_share(page, load, narration=False)
    page.evaluate(
        """() => {
          navigator.clipboard.writeText = () => Promise.reject(new Error('denied'));
          document.execCommand = command => {
            if(command === 'copy') sharedCopies.push(document.querySelector('body > textarea').value);
            return true;
          };
        }"""
    )
    copy = dialog.get_by_role("button", name="复制链接", exact=True)
    copy.focus()
    expect(page.get_by_role("tooltip", name="复制链接", exact=True)).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.get_by_text("分享链接已复制到剪贴板！", exact=True)).to_be_visible()
    assert page.evaluate("sharedCopies") == [SHARE_URL]
    assert page.locator("body > textarea").count() == 0
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("close", ["button", "header", "mask"])
def test_share_reopens_with_one_dialog_and_returns_focus(ui_page, close):
    page, load = ui_page
    state, dialog, trigger = open_share(page, load)
    for _ in range(3):
        expect(page.get_by_role("dialog")).to_have_count(1)
        if close == "mask":
            page.locator(".ant-modal-wrap").click(position=dict(x=4, y=4))
        else:
            dialog.get_by_role(
                "button",
                name="关闭" if close == "button" else "关闭分享弹窗",
                exact=True,
            ).click()
        expect(dialog).not_to_be_visible()
        expect(trigger).to_be_focused()
        assert page.locator(".lp-share-modal").count() == 0
        trigger.click()
        page.get_by_role("menuitem", name="分享链接", exact=True).click()
        expect(dialog).to_be_visible()
    assert not state["errors"] and not state["writes"]


def test_share_generation_failure_leaves_editor_usable(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.route(
        "**/share/generate",
        lambda route: route.fulfill(status=503, json={"detail": "不可用"}),
    )
    page.get_by_role("button", name="更多工具", exact=True).click()
    page.get_by_role("menuitem", name="分享链接", exact=True).click()
    expect(
        page.get_by_text("生成分享链接失败: 生成分享链接失败", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_role("button", name="保存", exact=True)).to_be_enabled()
    expect(page.get_by_text("正在生成分享链接...", exact=True)).not_to_be_visible()
    assert not state["errors"] and not state["writes"]


def test_share_url_is_text_and_focus_stays_in_dialog(ui_page):
    page, load = ui_page
    state = setup(page, load)
    unsafe = '/share/<img src=x onerror="window.shareInjected=true">'
    page.route(
        "**/share/generate", lambda route: route.fulfill(json={"share_url": unsafe})
    )
    page.evaluate("() => {showShareDialog()}")
    dialog = page.get_by_role("dialog", name="分享链接", exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("textbox", name="演示链接", exact=True)).to_have_value(
        "http://ui.test" + unsafe
    )
    assert not page.evaluate("!!window.shareInjected")
    assert page.locator(".lp-share-modal img").count() == 0
    for _ in range(12):
        page.keyboard.press("Tab")
        assert dialog.evaluate("e => e.contains(document.activeElement)")
    expect(page.get_by_text("正在生成分享链接...", exact=True)).not_to_be_visible()
    assert not state["errors"]


def test_share_native_fallback_keeps_original_actions_without_react(ui_page):
    page, load = ui_page
    page.route("**/static/antd/app.js*", lambda route: route.abort())
    state = setup(page, load, native=True)
    page.evaluate("() => {showShareDialog()}")
    modal = page.locator(".lp-share-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#lpShareUrlBox")).to_have_text(
        "http://ui.test/share/ui-editor"
    )
    expect(modal.get_by_role("button", name="复制链接", exact=True)).to_be_visible()
    expect(modal.get_by_role("button", name="禁用分享", exact=True)).to_be_visible()
    modal.get_by_role("button", name="关闭", exact=True).click()
    expect(modal).not_to_be_visible()
    page.evaluate("() => {showShareDialog()}")
    expect(modal).to_be_visible()
    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible()
    assert not state["errors"]
