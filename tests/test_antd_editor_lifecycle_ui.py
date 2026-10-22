"""Explicit editor state and lifecycle, exercised against compiled assets."""

import re
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import HTML, setup


def test_editor_actions_work_without_hidden_toolbar_or_dom_state_signals(ui_page):
    page, load = ui_page
    state = setup(page, load)
    assert (
        page.locator(
            ".editor-toolbar, .editor-header, #slideshowBtn, #saveSlideBtn, #slidesSidebarToggle"
        ).count()
        == 0
    )
    assert page.evaluate("typeof LandPPTEditorUI") == "undefined"
    # Native state changes notify React even when nothing mutates in the document.
    page.evaluate("currentSlideIndex = 1; LandPPTEditorEngine.changed()")
    expect(page.locator(".editor-ant-title")).to_contain_text("第 2 / 2 页")
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    assistant = page.get_by_role("dialog", name=re.compile("^AI 编辑助手"))
    expect(assistant).to_be_visible()
    expect(assistant).to_contain_text("第 2 页")
    page.keyboard.press("Escape")
    assert not state["errors"] and not state["writes"]


def test_only_current_page_is_saved_and_shortcut_cannot_duplicate_pending_write(
    ui_page,
):
    page, load = ui_page
    state = setup(page, load)
    page.locator(".slide-thumbnail").nth(1).click()
    page.get_by_role("toolbar").get_by_text("代码", exact=True).click()
    source = HTML.replace("原始演示内容", "只修改第二页")
    page.locator("#codeEditor").fill(source)
    held = []
    page.route("**/slides/*/save", lambda route: held.append(route))
    page.get_by_role("button", name="保存", exact=True).click()
    page.wait_for_timeout(50)
    page.evaluate("() => { saveSlide(); saveSlide(); }")
    assert len(held) == 1
    request = held[0].request
    assert request.url.endswith("/slides/1/save")
    assert request.post_data_json["html_content"] == source
    assert request.post_data_json["is_user_edited"] is True
    held[0].fulfill(json=dict(success=True))
    expect(page.get_by_role("button", name="保存", exact=True)).not_to_have_class(
        re.compile("ant-btn-loading")
    )
    page.wait_for_timeout(50)
    assert len(held) == 1 and not state["errors"]


def test_cached_return_restores_subscriptions_once_without_editing_requests(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.evaluate(
        "dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}))"
    )
    page.evaluate("currentSlideIndex = 1; LandPPTEditorEngine.changed()")
    expect(page.locator(".editor-ant-title")).to_contain_text("第 1 / 2 页")
    page.evaluate(
        "dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true})); dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))"
    )
    expect(page.locator(".editor-ant-title")).to_contain_text("第 2 / 2 页")
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(page.locator(".editor-ant-assistant")).to_be_visible()
    page.keyboard.press("Escape")
    page.locator(".slide-thumbnail").first.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".editor-ant-title")).to_contain_text("第 1 / 2 页")
    assert not state["writes"] and not state["errors"]
