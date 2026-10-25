"""Outline navigation shares the real editor's page selection and draft identity."""

from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_documents_ui import document_setup, panel


TITLES = [
    "封面",
    "背景与目标",
    "行业资料",
    "目标总结",
    "实施计划",
    "流程与职责",
    "时间安排",
    "交付验收",
]


def navigation_setup(page, load, **options):
    state = document_setup(page, load, slide_count=8, **options)
    for index, title in enumerate(TITLES):
        state["outlines"][index].update(
            title=title, slide_type="transition" if index in [1, 4] else "content"
        )
    page.evaluate(
        """outlines => {
        projectOutline.slides=outlines;
        slidesData.forEach((slide,index)=>{slide.title=outlines[index].title;slide.slide_type=outlines[index].slide_type;});
        refreshSidebar(); LandPPTEditorEngine.changed();
    }""",
        state["outlines"],
    )
    return state


def directory(page):
    return page.get_by_role("region", name="文稿目录", exact=True)


def choose_page(page, title, index):
    directory(page).get_by_text(title, exact=True).click()
    page.wait_for_function("expected=>currentSlideIndex===expected", arg=index)
    expect(directory(page).locator(".ant-tree-treenode-selected")).to_contain_text(
        title
    )


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (390, 844), (320, 568), (844, 390)]
)
@pytest.mark.parametrize("svg", [False, True])
def test_tree_search_fold_and_locate_use_existing_page_selection_without_writes(
    ui_page, width, height, svg
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = navigation_setup(page, load, svg=svg)
    original = page.evaluate("slidesData.map(slide=>slide.html_content)")
    panel(page, "目录")
    region = directory(page)
    expect(region.get_by_role("status")).to_contain_text("8 页 · 2 个章节")
    expect(region.get_by_role("tree", name="章节与页面")).to_be_visible()
    assert state["document_reads"] == []
    chapter = region.locator(".ant-tree-treenode").filter(
        has=page.get_by_text("背景与目标", exact=True)
    )
    chapter.locator(".ant-tree-switcher").click()
    expect(region.get_by_text("行业资料", exact=True)).to_have_count(0)
    panel(page, "幻灯片")
    panel(page, "目录")
    expect(region.get_by_text("行业资料", exact=True)).to_have_count(0)
    search = region.get_by_role("textbox", name="搜索文稿目录", exact=True)
    search.fill("职责")
    expect(region.get_by_text("实施计划", exact=True)).to_be_visible()
    choose_page(page, "流程与职责", 5)
    region.get_by_role("button", name="定位当前页", exact=True).click()
    expect(search).to_have_value("")
    expect(region.locator(".ant-tree-treenode-selected")).to_be_in_viewport()
    expect(region.get_by_role("status")).to_contain_text("当前第 6 页")
    search.fill("不存在的标题")
    expect(region.get_by_text("没有匹配的页面", exact=True)).to_be_visible()
    region.get_by_role("button", name="清除搜索", exact=True).click()
    search.fill("8")
    choose_page(page, "交付验收", 7)
    region.get_by_role("button", name="定位当前页", exact=True).click()
    assert region.evaluate("e=>e.scrollWidth<=e.clientWidth")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    expect(page.locator(".project-stages")).to_have_count(0)
    assert page.evaluate("slidesData.map(slide=>slide.html_content)") == original
    assert (
        not state["writes"]
        and not state["document_writes"]
        and not state["document_reads"]
        and not state["errors"]
    )
    if not svg:
        output = Path("artifacts/editor-outline-navigation-20261022")
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(output / f"directory-{width}x{height}.png"), animations="disabled"
        )


def test_directory_keeps_outline_and_language_drafts_until_explicit_save(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "大纲")
    editor = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(editor).to_have_value("封面")
    editor.fill("未保存的封面标题")
    panel(page, "目录")
    choose_page(page, "流程与职责", 5)
    panel(page, "讲稿")
    page.get_by_role("button", name="撰写讲稿", exact=True).click()
    page.get_by_role("textbox", name="讲稿正文", exact=True).fill("本页中文讲稿草稿")
    panel(page, "目录")
    choose_page(page, "封面", 0)
    panel(page, "大纲")
    expect(editor).to_have_value("未保存的封面标题")
    assert not state["document_writes"] and not state["writes"]
    page.get_by_role("button", name="保存大纲", exact=True).first.click()
    expect(page.get_by_role("status").filter(has_text="与服务器同步")).to_be_visible()
    panel(page, "目录")
    expect(directory(page).get_by_text("未保存的封面标题", exact=True)).to_be_visible()
    choose_page(page, "流程与职责", 5)
    panel(page, "讲稿")
    expect(page.get_by_role("textbox", name="讲稿正文", exact=True)).to_have_value(
        "本页中文讲稿草稿"
    )
    assert (
        len(state["document_writes"]) == 1
        and state["document_writes"][0][2]["kind"] == "outline"
    )
    assert not state["writes"] and not state["errors"]


def test_keyboard_selects_chapter_and_saved_page_type_updates_grouping(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "目录")
    region = directory(page)
    choose_page(page, "背景与目标", 1)
    tree = region.get_by_role("tree", name="章节与页面")
    tree.focus()
    active = region.locator(".ant-tree-treenode-active")
    page.keyboard.press("Home")
    expect(active).to_contain_text("封面")
    page.keyboard.press("ArrowDown")
    expect(active).to_contain_text("背景与目标")
    page.keyboard.press("ArrowLeft")
    expect(region.get_by_text("行业资料", exact=True)).to_have_count(0)
    page.keyboard.press("ArrowRight")
    expect(region.get_by_text("行业资料", exact=True)).to_be_visible()
    page.keyboard.press("ArrowDown")
    expect(active).to_contain_text("行业资料")
    page.keyboard.press("Enter")
    page.wait_for_function("currentSlideIndex===2")
    panel(page, "大纲")
    select = page.get_by_role("combobox", name="大纲页面类型", exact=True)
    select.click()
    page.get_by_text("章节过渡页", exact=True).last.click()
    page.get_by_role("button", name="保存大纲", exact=True).first.click()
    expect(page.get_by_role("status").filter(has_text="与服务器同步")).to_be_visible()
    panel(page, "目录")
    expect(region.get_by_role("status")).to_contain_text("3 个章节")
    assert (
        len(state["document_writes"]) == 1
        and not state["writes"]
        and not state["errors"]
    )


def test_empty_and_flat_decks_do_not_invent_chapters(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "目录")
    region = directory(page)
    expect(region.get_by_role("status")).to_contain_text("2 页")
    expect(region.get_by_role("status")).not_to_contain_text("章节")
    assert region.locator(".ant-tree-switcher-noop").count() == 2
    assert not state["document_reads"] and not state["writes"]
    # A fresh empty editor mounts the same tab without dereferencing a page.
    state = document_setup(page, load, empty=True)
    panel(page, "目录")
    expect(directory(page).get_by_text("暂无幻灯片", exact=True)).to_be_visible()
    expect(
        directory(page).get_by_role("button", name="定位当前页", exact=True)
    ).to_be_disabled()
    assert not state["document_reads"] and not state["errors"]


def test_native_refresh_reorders_directory_without_using_filtered_positions(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "目录")
    choose_page(page, "交付验收", 7)
    page.evaluate(
        """() => {
        const slide=slidesData.splice(7,1)[0], outline=projectOutline.slides.splice(7,1)[0];
        slidesData.splice(2,0,slide); projectOutline.slides.splice(2,0,outline);
        currentSlideIndex=2; refreshSidebar(); LandPPTEditorEngine.changed();
    }"""
    )
    expect(directory(page).get_by_role("status")).to_contain_text(
        "当前第 3 页 · 交付验收"
    )
    directory(page).get_by_role("textbox", name="搜索文稿目录", exact=True).fill(
        "行业资料"
    )
    choose_page(page, "行业资料", 3)
    assert not state["writes"] and not state["document_reads"] and not state["errors"]


def test_directory_save_shortcut_saves_canvas_without_submitting_text_drafts(ui_page):
    page, load = ui_page
    state = navigation_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    title.fill("仍保留的文稿草稿")
    panel(page, "目录")
    directory(page).get_by_role("textbox", name="搜索文稿目录", exact=True).press(
        "Control+s"
    )
    expect(page.get_by_text("幻灯片已保存！", exact=True)).to_be_visible()
    assert len(state["writes"]) == 1 and not state["document_writes"]
    panel(page, "大纲")
    expect(title).to_have_value("仍保留的文稿草稿")
    assert not state["errors"]
