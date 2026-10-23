"""Native structure overview shares stable page identities, without I/O."""

from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_documents_ui import document_setup, panel
from test_antd_editor_outline_batch_ui import check_page
from test_antd_editor_outline_navigation_ui import TITLES, directory, navigation_setup

OUT = Path("artifacts/editor-outline-overview-20261023")


def overview(page):
    directory(page).get_by_role("button", name="结构总览", exact=True).click()
    dialog = page.get_by_role("dialog", name="文稿结构总览", exact=True)
    expect(dialog).to_be_visible()
    return dialog


@pytest.mark.parametrize("size", [(1440, 900), (390, 844), (320, 568), (844, 390)])
@pytest.mark.parametrize("svg", [False, True])
def test_overview_groups_search_and_jump_with_no_requests_or_artwork_changes(
    ui_page, size, svg
):
    page, load = ui_page
    page.set_viewport_size(dict(zip(["width", "height"], size)))
    state = navigation_setup(page, load, svg=svg)
    original = page.evaluate("slidesData.map(slide=>slide.html_content)")
    panel(page, "目录")
    directory(page).get_by_role("textbox", name="搜索文稿目录", exact=True).fill("职责")
    dialog = overview(page)
    expect(dialog.get_by_text("8 页 · 2 个章节", exact=True)).to_be_visible()
    region = dialog.get_by_role("region", name="章节结构卡片", exact=True)
    expect(region.locator(".ant-card")).to_have_count(3)
    expect(region.get_by_role("button")).to_have_count(8)
    expect(region.get_by_text("未分章节", exact=True)).to_be_visible()
    assert region.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    if size[0] <= 390:
        assert region.get_by_role("button").first.bounding_box()["height"] >= 44
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(OUT / f"overview-{size[0]}x{size[1]}-{'svg' if svg else 'html'}.png"),
        animations="disabled",
    )
    search = dialog.get_by_role("textbox", name="搜索结构总览", exact=True)
    search.fill("不存在")
    expect(dialog.get_by_text("没有匹配的页面", exact=True)).to_be_visible()
    dialog.get_by_role("button", name="在结构总览定位当前页", exact=True).click()
    expect(search).to_have_value("")
    expect(region.locator('[aria-current="page"]')).to_be_focused()
    expect(region.locator('[aria-current="page"]')).to_be_in_viewport()
    search.click()
    search.press_sequentially("封面")
    expect(search).to_have_value("封面")
    expect(search).to_be_focused()
    search.fill("实施计划")
    expect(region.get_by_role("button")).to_have_count(4)
    search.fill("职责")
    expect(region.get_by_role("button")).to_have_count(
        2
    )  # Includes its explicit chapter.
    region.get_by_role("button", name="转到第 6 页：流程与职责", exact=True).click()
    expect(dialog).not_to_be_visible()
    page.wait_for_function("currentSlideIndex===5")
    expect(
        directory(page).get_by_role("textbox", name="搜索文稿目录", exact=True)
    ).to_have_value("职责")
    expect(
        directory(page).get_by_role("button", name="结构总览", exact=True)
    ).to_be_focused()
    assert page.evaluate("slidesData.map(slide=>slide.html_content)") == original
    assert (
        not state["document_reads"]
        and not state["document_writes"]
        and not state["writes"]
        and not state["errors"]
    )


def test_modal_keyboard_cannot_save_navigate_or_clear_directory_multiselection(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "目录")
    directory(page).get_by_role("button", name="批量编辑", exact=True).click()
    check_page(page, "封面")
    check_page(page, "流程与职责")
    dialog = overview(page)
    search = dialog.get_by_role("textbox", name="搜索结构总览", exact=True)
    expect(
        dialog.locator(".ant-drawer-footer").get_by_role(
            "button", name="关闭", exact=True
        )
    ).to_be_focused()
    page.keyboard.press("Control+s")
    search.focus()
    page.keyboard.press("Control+s")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Delete")
    assert page.evaluate("currentSlideIndex") == 0
    dialog.get_by_role("button", name="在结构总览定位当前页", exact=True).hover()
    expect(page.get_by_role("tooltip")).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(directory(page).get_by_text("已选 2 页", exact=True)).to_be_visible()
    expect(
        directory(page).get_by_role("button", name="结构总览", exact=True)
    ).to_be_focused()
    assert not state["writes"] and not state["document_writes"] and not state["errors"]


def test_overview_navigation_keeps_hidden_outline_and_speech_drafts(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    title.fill("保留的大纲草稿")
    panel(page, "讲稿")
    page.get_by_role("button", name="编辑文稿", exact=True).click()
    speech = page.get_by_role("textbox", name="讲稿正文", exact=True)
    speech.fill("保留的讲稿草稿")
    panel(page, "目录")
    dialog = overview(page)
    dialog.get_by_role("button", name="转到第 8 页：交付验收", exact=True).click()
    page.wait_for_function("currentSlideIndex===7")
    dialog = overview(page)
    dialog.get_by_role("button", name="转到第 1 页：封面", exact=True).click()
    page.wait_for_function("currentSlideIndex===0")
    panel(page, "大纲")
    expect(title).to_have_value("保留的大纲草稿")
    panel(page, "讲稿")
    expect(speech).to_have_value("保留的讲稿草稿")
    assert not state["writes"] and not state["document_writes"] and not state["errors"]


def test_live_metadata_reorder_uses_real_indices_and_updates_chapter_count(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "目录")
    dialog = overview(page)
    page.evaluate(
        """() => {
      projectOutline.slides[3].slide_type='transition'; slidesData[3].slide_type='transition';
      const slide=slidesData.splice(7,1)[0], outline=projectOutline.slides.splice(7,1)[0];
      slidesData.splice(2,0,slide); projectOutline.slides.splice(2,0,outline);
      currentSlideIndex=2; refreshSidebar(); LandPPTEditorEngine.changed();
    }"""
    )
    expect(dialog.get_by_text("8 页 · 3 个章节", exact=True)).to_be_visible()
    expect(dialog.locator('[aria-current="page"]')).to_have_attribute(
        "aria-label", "转到第 3 页：交付验收"
    )
    dialog.get_by_role("textbox", name="搜索结构总览", exact=True).fill("行业资料")
    dialog.get_by_role("button", name="转到第 4 页：行业资料", exact=True).click()
    page.wait_for_function("currentSlideIndex===3")
    assert not state["document_reads"] and not state["writes"] and not state["errors"]


def test_flat_and_empty_decks_do_not_gain_fake_chapters(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "目录")
    dialog = overview(page)
    expect(dialog.get_by_text("2 页 · 0 个章节", exact=True)).to_be_visible()
    expect(dialog.get_by_text("全部页面", exact=True)).to_be_visible()
    expect(
        dialog.get_by_role("region", name="章节结构卡片").get_by_role("button")
    ).to_have_count(2)
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    state = document_setup(page, load, empty=True)
    panel(page, "目录")
    expect(
        directory(page).get_by_role("button", name="结构总览", exact=True)
    ).to_be_disabled()
    assert not state["document_reads"] and not state["errors"]


@pytest.mark.parametrize("svg", [False, True])
def test_long_and_hostile_titles_are_plain_text_and_fit_mobile_cards(ui_page, svg):
    page, load = ui_page
    page.set_viewport_size(dict(width=320, height=568))
    state = navigation_setup(page, load, svg=svg)
    names = ["很长的标题" * 80, '<img src=x onerror="window.overviewInjected=true">']
    page.evaluate(
        """names=>{names.forEach((name,index)=>{slidesData[index].title=name;projectOutline.slides[index].title=name;});refreshSidebar();LandPPTEditorEngine.changed();}""",
        names,
    )
    panel(page, "目录")
    dialog = overview(page)
    expect(
        dialog.get_by_role("button", name=f"转到第 2 页：{names[1]}", exact=True)
    ).to_be_visible()
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    assert page.evaluate("!window.overviewInjected")
    expect(
        page.locator('.slide-thumbnail[data-slide-index="1"] .slide-title')
    ).to_contain_text(names[1])
    expect(page.locator(".slide-thumbnail .slide-title img")).to_have_count(0)
    if svg:
        expect(page.locator(".slide-thumbnail .slide-mode-badge")).to_have_count(8)
    expect(dialog.locator("img,iframe,object,script")).to_have_count(0)
    dialog.get_by_role("textbox", name="搜索结构总览", exact=True).fill("8")
    dialog.get_by_role("button", name="转到第 8 页：交付验收", exact=True).click()
    page.wait_for_function("currentSlideIndex===7")
    assert not state["document_reads"] and not state["writes"] and not state["errors"]


def test_hiding_directory_closes_its_portal_without_stealing_focus(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "目录")
    dialog = overview(page)
    page.locator(".editor-document-tabs").get_by_text("幻灯片", exact=True).evaluate(
        "e=>e.click()"
    )
    expect(dialog).not_to_be_visible()
    expect(directory(page)).not_to_be_visible()
    assert not state["document_reads"] and not state["writes"] and not state["errors"]


def test_closed_overview_releases_shortcut_handler_back_to_editor(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "目录")
    dialog = overview(page)
    page.keyboard.press("Control+s")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert not state["writes"]
    directory(page).get_by_role("textbox", name="搜索文稿目录", exact=True).press(
        "Control+s"
    )
    expect(page.get_by_text("幻灯片已保存！", exact=True)).to_be_visible()
    assert (
        len(state["writes"]) == 1
        and not state["document_writes"]
        and not state["errors"]
    )
