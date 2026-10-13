"""Thumbnail menu geometry, keyboard access and native operation boundaries."""

import json

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import HTML, SVG_HTML, setup

SIZES = [(1910, 915), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


def open_menu(page, index=1, point=None, key=None):
    if page.evaluate(
        "document.querySelector('.editor-container').classList.contains('sidebar-collapsed')"
    ):
        page.get_by_role("button", name="展开或收起幻灯片列表").click()
    thumbnail = page.locator(".slide-thumbnail").nth(index)
    if key:
        thumbnail.focus()
        page.keyboard.press(key)
    elif point:
        thumbnail.evaluate(
            '(node, point) => node.dispatchEvent(new MouseEvent("contextmenu", '
            "{clientX:point[0], clientY:point[1], button:2, bubbles:true, cancelable:true}))",
            point,
        )
    else:
        thumbnail.click(button="right")
    menu = page.locator(".editor-thumbnail-menu")
    expect(menu).to_be_visible()
    expect(menu.get_by_role("menuitem", name="编辑代码")).to_be_focused()
    return menu


def outline_api(page):
    writes = []

    def save(route):
        writes.append(route.request.post_data_json)
        route.fulfill(json=dict(status="success"))

    page.route("**/projects/ui-editor/update-outline", save)
    return writes


def slides_and_outline(page):
    return page.evaluate("({slides: slidesData, outline: projectOutline.slides})")


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("corner", ["actual", "top-left", "bottom-right"])
def test_context_menu_stays_in_viewport_without_changing_selection_or_artwork(
    ui_page, width, height, corner
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load)
    original = slides_and_outline(page)
    frame = page.locator("#slideFrame").get_attribute("srcdoc")
    point = {"top-left": [1, 1], "bottom-right": [width - 1, height - 1]}.get(corner)
    menu = open_menu(page, point=point)
    box = menu.bounding_box()
    assert box["x"] >= 0 and box["y"] >= 0
    assert box["x"] + box["width"] <= width
    assert box["y"] + box["height"] <= height
    assert menu.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(menu.locator("header")).to_contain_text("实施计划")
    expect(menu.get_by_role("menuitem")).to_have_count(9)
    expect(menu.get_by_role("menuitem", name="粘贴到此页之后")).to_have_attribute(
        "aria-disabled", "true"
    )
    assert not page.locator("#contextMenu").is_visible()
    assert page.evaluate("currentSlideIndex") == 0
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
    expect(page.locator(".slide-thumbnail").nth(1)).to_be_focused()
    assert slides_and_outline(page) == original
    assert page.locator("#slideFrame").get_attribute("srcdoc") == frame
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("key", ["Shift+F10", "ContextMenu"])
@pytest.mark.parametrize("svg", [False, True])
def test_keyboard_opens_menu_skips_disabled_item_and_keeps_multiselection(
    ui_page, key, svg
):
    page, load = ui_page
    state = setup(page, load, svg=svg)
    page.locator(".slide-thumbnail").nth(1).click(modifiers=["Control"])
    selected = page.evaluate("Array.from(selectedSlideIndices)")
    menu = open_menu(page, key=key)
    page.keyboard.press("ArrowDown")
    expect(menu.get_by_role("menuitem", name="重新生成", exact=True)).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(menu.get_by_role("menuitem", name="复制到剪贴板")).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(menu.get_by_role("menuitem", name="创建副本")).to_be_focused()
    page.keyboard.press("End")
    expect(menu.get_by_role("menuitem", name="删除幻灯片")).to_be_focused()
    page.keyboard.press("Home")
    expect(menu.get_by_role("menuitem", name="编辑代码")).to_be_focused()
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
    assert page.evaluate("Array.from(selectedSlideIndices)") == selected
    expect(page.locator(".slide-thumbnail").nth(1)).to_be_focused()
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("method", ["Tab", "click", "context", "scroll", "resize"])
def test_menu_closes_and_can_reopen_after_leaving_thumbnail_context(ui_page, method):
    page, load = ui_page
    state = setup(page, load)
    menu = open_menu(page)
    if method == "Tab":
        page.keyboard.press("Tab")
        expect(page.locator(".slide-thumbnail").nth(1)).to_be_focused()
    elif method == "click":
        page.locator(".editor-ant-title h1").click()
    elif method == "context":
        page.locator(".editor-ant-title h1").click(button="right")
    elif method == "scroll":
        page.locator(".slides-container").dispatch_event("scroll")
    else:
        page.set_viewport_size(dict(width=1024, height=768))
    expect(menu).not_to_be_visible()
    open_menu(page, index=0)
    expect(menu.locator("header")).to_contain_text("封面")
    page.keyboard.press("Escape")
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("svg", [False, True])
def test_copy_and_paste_preserve_target_source_and_outline(ui_page, svg):
    page, load = ui_page
    state = setup(page, load, svg=svg)
    operations = outline_api(page)
    original = slides_and_outline(page)
    menu = open_menu(page)
    page.keyboard.press("ArrowDown")
    expect(menu.get_by_role("menuitem", name="重新生成", exact=True)).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(menu.get_by_role("menuitem", name="复制到剪贴板")).to_be_focused()
    page.keyboard.press("Enter")
    expect(menu).not_to_be_visible()
    page.wait_for_function("copiedSlideData !== null")
    assert not state["writes"] and not operations
    assert page.evaluate("currentSlideIndex") == 0
    menu = open_menu(page, index=0)
    expect(menu.get_by_role("menuitem", name="粘贴到此页之后")).to_have_attribute(
        "aria-disabled", "false"
    )
    menu.get_by_role("menuitem", name="粘贴到此页之后").click()
    expect(page.locator(".slide-thumbnail")).to_have_count(3)
    page.wait_for_function("slidesData.every(s => s.is_user_edited)")
    result = slides_and_outline(page)
    assert result["slides"][1]["title"] == "实施计划 (副本)"
    assert result["slides"][1]["html_content"] == original["slides"][1]["html_content"]
    assert result["slides"][1]["render_mode"] == original["slides"][1]["render_mode"]
    assert (
        result["outline"][1]["content_points"]
        == original["outline"][1]["content_points"]
    )
    assert result["outline"][1]["description"] == original["outline"][1]["description"]
    assert [slide["page_number"] for slide in result["slides"]] == [1, 2, 3]
    assert [slide["page_number"] for slide in result["outline"]] == [1, 2, 3]
    assert operations[0]["operation"]["type"] == "insert"
    assert operations[0]["operation"]["slide_index"] == 1
    assert state["writes"] and not state["errors"]


@pytest.mark.parametrize("svg", [False, True])
def test_duplicate_uses_right_clicked_page_while_another_page_is_selected(ui_page, svg):
    page, load = ui_page
    state = setup(page, load, svg=svg)
    operations = outline_api(page)
    original = slides_and_outline(page)
    open_menu(page).get_by_role("menuitem", name="创建副本").click()
    expect(page.locator(".slide-thumbnail")).to_have_count(3)
    page.wait_for_function("slidesData.every(s => s.is_user_edited)")
    result = slides_and_outline(page)
    assert result["slides"][2]["title"] == "实施计划 (副本)"
    assert result["slides"][2]["html_content"] == original["slides"][1]["html_content"]
    assert (
        result["outline"][2]["content_points"]
        == original["outline"][1]["content_points"]
    )
    assert operations[0]["operation"]["slide_index"] == 2
    assert page.evaluate("currentSlideIndex") == 0
    assert state["writes"] and not state["errors"]


def test_insert_and_delete_still_use_native_outline_save_and_confirmation(ui_page):
    page, load = ui_page
    state = setup(page, load)
    operations = outline_api(page)
    original = slides_and_outline(page)
    open_menu(page, index=0).get_by_role("menuitem", name="插入新幻灯片").click()
    expect(page.locator(".slide-thumbnail")).to_have_count(3)
    page.wait_for_function("slidesData.every(s => s.is_user_edited)")
    inserted = slides_and_outline(page)
    assert "新建幻灯片" in inserted["slides"][1]["html_content"]
    assert inserted["outline"][1]["content_points"] == []
    open_menu(page).get_by_role("menuitem", name="删除幻灯片").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("确定要删除这张幻灯片吗")
    dialog.get_by_role("button", name="确认", exact=True).click()
    expect(page.locator(".slide-thumbnail")).to_have_count(2)
    page.wait_for_function(
        "slidesData.length === 2 && slidesData.every(s => s.is_user_edited)"
    )
    result = slides_and_outline(page)
    assert [s["html_content"] for s in result["slides"]] == [
        s["html_content"] for s in original["slides"]
    ]
    assert result["outline"] == original["outline"]
    assert [row["operation"]["type"] for row in operations] == ["insert", "delete"]
    assert not state["errors"]


@pytest.mark.parametrize("label", ["删除幻灯片", "重新生成"])
def test_canceling_destructive_actions_does_not_write_and_returns_focus(ui_page, label):
    page, load = ui_page
    state = setup(page, load)
    original = slides_and_outline(page)
    open_menu(page).get_by_role("menuitem", name=label, exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    if label == "重新生成":
        expect(dialog).to_contain_text("实施计划")
    dialog.get_by_role("button", name="取消", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator(".slide-thumbnail").nth(1)).to_be_focused()
    assert slides_and_outline(page) == original
    assert not state["writes"] and not state["errors"]


def test_native_disabled_and_hidden_actions_cannot_be_invoked_by_adapter(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.evaluate(
        """() => {
      hasSlidesData = false; updateFunctionButtonsState();
      document.querySelector('#contextMenu [onclick="exportSingleSlidePptxClient()"]').hidden = true;
    }"""
    )
    menu = open_menu(page)
    for label in [
        "复制到剪贴板",
        "粘贴到此页之后",
        "创建副本",
        "插入新幻灯片",
        "删除幻灯片",
    ]:
        expect(menu.get_by_role("menuitem", name=label)).to_have_attribute(
            "aria-disabled", "true"
        )
        assert "PPT生成完成" in menu.get_by_role("menuitem", name=label).get_attribute(
            "title"
        )
    expect(menu.get_by_role("menuitem", name="导出单页 PPTX")).to_have_count(0)
    original = slides_and_outline(page)
    page.evaluate(
        """() => {
      LandPPTEditorUI.runContextAction('duplicateSlide');
      LandPPTEditorUI.runContextAction('exportSingleSlidePptxClient');
      LandPPTEditorUI.runContextAction('saveToServer');
    }"""
    )
    assert slides_and_outline(page) == original
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("svg", [False, True])
def test_edit_and_html_export_keep_the_right_clicked_source(ui_page, tmp_path, svg):
    page, load = ui_page
    state = setup(page, load, svg=svg)
    source = SVG_HTML if svg else HTML
    menu = open_menu(page)
    with page.expect_download() as downloaded:
        menu.get_by_role("menuitem", name="导出 HTML").click()
    download = downloaded.value
    target = tmp_path / "slide.html"
    download.save_as(target)
    assert download.suggested_filename == "slide_2_实施计划.html"
    assert target.read_text(encoding="utf-8") == source
    open_menu(page).get_by_role("menuitem", name="编辑代码").click()
    page.wait_for_function("currentSlideIndex === 1 && currentMode === 'edit'")
    assert page.locator("#slideFrame").get_attribute("srcdoc") == source
    assert not state["writes"] and not state["errors"]


def test_client_pptx_export_receives_the_context_page_index(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.evaluate(
        """() => {
      window.exportTarget = null;
      window.exportSlidesToPptxClient = options => { window.exportTarget = options; };
    }"""
    )
    open_menu(page).get_by_role("menuitem", name="导出单页 PPTX").click()
    page.wait_for_function("window.exportTarget !== null")
    assert page.evaluate("exportTarget") == dict(slideIndices=[1])
    assert page.evaluate("currentSlideIndex") == 0
    assert not state["writes"] and not state["errors"]


def test_menu_title_wrap_does_not_widen_menu_and_last_slide_guard_is_preserved(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.set_viewport_size(dict(width=320, height=568))
    page.evaluate(
        """() => {
      slidesData[0].title = '超长幻灯片标题' .repeat(40);
      slidesData.splice(1); projectOutline.slides.splice(1); refreshSidebar();
    }"""
    )
    menu = open_menu(page, index=0)
    assert menu.bounding_box()["width"] <= 304
    assert (
        menu.locator("header strong")
        .get_attribute("title")
        .startswith("超长幻灯片标题")
    )
    menu.get_by_role("menuitem", name="删除幻灯片").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.locator(".slide-thumbnail")).to_have_count(1)
    assert not state["writes"] and not state["errors"]


def test_native_menu_remains_available_when_react_assets_cannot_load(ui_page):
    page, load = ui_page
    page.route("**/static/antd/**", lambda route: route.abort())
    state = setup(page, load, native=True)
    original = slides_and_outline(page)
    page.locator(".slide-thumbnail").nth(1).click(button="right")
    menu = page.locator("#contextMenu")
    expect(menu).to_be_visible()
    expect(menu.locator(".context-menu-item")).to_have_count(9)
    expect(menu.locator("#pasteMenuItem")).to_have_class("context-menu-item disabled")
    menu.get_by_text("复制幻灯片", exact=True).click()
    expect(menu).not_to_be_visible()
    assert page.evaluate("copiedSlideData.title") == "实施计划"
    assert slides_and_outline(page) == original
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("width,height", [(844, 280), (320, 390)])
def test_short_window_can_scroll_to_last_action_without_closing_menu(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load)
    menu = open_menu(page)
    page.keyboard.press("End")
    last = menu.get_by_role("menuitem", name="删除幻灯片")
    expect(last).to_be_focused()
    expect(menu).to_be_visible()
    box = last.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert menu.evaluate(
        "e => [e, ...e.querySelectorAll('*')].some(node => node.scrollTop > 0)"
    )
    assert page.evaluate("scrollY") == 0
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
    expect(page.locator(".slide-thumbnail").nth(1)).to_be_focused()
    assert not state["writes"] and not state["errors"]
