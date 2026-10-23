"""Real sidebar/iframe UI with isolated document reads and writes."""

import copy
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import HTML, SVG_HTML, setup

SIZES = [(1920, 1080), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def document_setup(page, load, svg=False, empty=False, slide_count=2):
    state = setup(page, load, svg=svg, empty=empty, slide_count=slide_count)
    state.update(
        document_reads=[], document_writes=[], document_fail=False, conflict=False
    )
    outlines = [
        dict(
            title="封面",
            slide_type="title",
            content_points=["确认目标", "组织实施"],
            description="说明核心内容",
            custom={"layout": "keep"},
        ),
        dict(
            title="实施计划",
            slide_type="custom-section",
            content_points=["第二页内容"],
            description="保留说明",
        ),
    ]
    outlines.extend(
        dict(
            title=f"实施阶段 {i + 1}", slide_type="content", content_points=["阶段目标"]
        )
        for i in range(2, slide_count)
    )
    scripts = {
        (0, "zh"): dict(
            id=1,
            slide_index=0,
            language="zh",
            slide_title="封面",
            script_content="介绍核心目标与实施过程。\n讲稿只显示一次。",
            estimated_duration="2分钟",
            speaker_notes="停顿后继续",
        )
    }
    state.update(outlines=outlines, scripts=scripts)

    def api(route):
        req = route.request
        url = urlsplit(req.url)
        index = int(url.path.rsplit("/", 1)[1])
        language = parse_qs(url.query)["language"][0]
        if req.method == "GET":
            state["document_reads"].append((index, language))
        else:
            body = req.post_data_json
            state["document_writes"].append((index, language, body))
        if state["document_fail"]:
            route.fulfill(status=503, json={"detail": "文稿服务暂时不可用"})
            return
        if req.method == "PATCH":
            if state["conflict"]:
                route.fulfill(
                    status=409, json={"detail": "内容已在其他窗口更新；草稿已保留"}
                )
                return
            if body["kind"] == "outline":
                outlines[index].update(body["outline"])
            else:
                scripts[index, language] = {
                    **body["speech"],
                    "id": index + 10,
                    "slide_index": index,
                    "language": language,
                }
        script = scripts.get((index, language))
        route.fulfill(
            json={
                "success": True,
                "document": {
                    "slide_index": index,
                    "slide_id": f"stable-{index}",
                    "language": language,
                    "outline": copy.deepcopy(outlines[index]),
                    "script": script,
                    "outline_revision": revision(outlines[index]),
                    "speech_revision": revision(script),
                },
            }
        )

    page.route("**/editor-documents/*?*", api)
    return state


def panel(page, name):
    if page.locator(".editor-container").evaluate("node=>node.classList.contains('sidebar-collapsed')"):
        page.get_by_role("button", name="展开或收起幻灯片列表").click()
    page.locator(".editor-document-tabs").get_by_text(name, exact=True).click()


def next_page(page):
    page.get_by_role("button", name="下一页", exact=True).click()


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("svg", [False, True])
def test_sidebar_layout_modes_and_artwork_unchanged(ui_page, size, svg):
    page, load = ui_page
    page.set_viewport_size(dict(zip(("width", "height"), size)))
    state = document_setup(page, load, svg=svg)
    assert state["document_reads"] == []  # Text is fetched only on demand.
    original = page.evaluate("slidesData.map(slide=>slide.html_content)")
    panel(page, "幻灯片")
    sidebar = page.locator("#slidesSidebar")
    initial_box = sidebar.bounding_box()
    canvas = page.locator(".editor-content").bounding_box()
    panel(page, "大纲")
    expect(page.get_by_role("textbox", name="大纲标题", exact=True)).to_have_value(
        "封面"
    )
    assert sidebar.bounding_box()["width"] <= min(336, size[0] - 24) + 1
    assert sidebar.bounding_box()["width"] == pytest.approx(initial_box["width"], abs=1)
    footer = page.locator(".editor-document-footer")
    box = footer.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= size[1] + 1
    assert page.locator(".slides-container").is_hidden()
    page.get_by_role("button", name="阅读文稿", exact=True).click()
    expect(page.locator(".editor-document-reading h2")).to_have_text("封面")
    panel(page, "讲稿")
    assert sidebar.bounding_box()["width"] == pytest.approx(initial_box["width"], abs=1)
    expect(page.locator(".editor-document-reading p").first).to_contain_text(
        "讲稿只显示一次"
    )
    assert (
        page.locator(".editor-document-reading")
        .get_by_text(re.compile("介绍核心目标"))
        .count()
        == 1
    )
    page.get_by_role("button", name="编辑文稿", exact=True).click()
    expect(page.get_by_role("textbox", name="讲稿正文", exact=True)).to_contain_text(
        "讲稿只显示一次"
    )
    panel(page, "幻灯片")
    expect(page.locator(".slide-thumbnail").first).to_be_visible()
    assert sidebar.bounding_box() == initial_box
    assert page.locator(".editor-content").bounding_box() == canvas
    assert page.evaluate("slidesData.map(slide=>slide.html_content)") == original
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert (
        state["document_writes"] == []
        and state["writes"] == []
        and state["errors"] == []
    )


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("svg", [False, True])
def test_long_slide_list_and_documents_scroll_with_fixed_tabs_and_footer(
    ui_page, size, svg
):
    page, load = ui_page
    page.set_viewport_size(dict(zip(("width", "height"), size)))
    state = document_setup(page, load, svg=svg, slide_count=12)
    state["outlines"][0]["content_points"] = [
        f"第 {i + 1} 项实施要点" for i in range(24)
    ]
    state["scripts"][0, "zh"]["script_content"] = "长讲稿需要可以滚动阅读。\n" * 100
    panel(page, "幻灯片")
    tabs = page.locator(".editor-document-tabs")
    tabs_box = tabs.bounding_box()
    sidebar = page.locator("#slidesSidebar")
    sidebar_box = sidebar.bounding_box()
    slides = page.locator(".slides-container")
    assert slides.evaluate("node => node.scrollHeight > node.clientHeight + 100")
    slides.hover()
    page.mouse.wheel(0, 100000)
    page.wait_for_function(
        "() => {const node=document.querySelector('.slides-container');return node.scrollTop > 100 && node.scrollTop + node.clientHeight >= node.scrollHeight - 2}"
    )
    last = page.locator(".slide-thumbnail").last.bounding_box()
    assert last["y"] + last["height"] <= size[1] + 1
    assert tabs.bounding_box() == tabs_box
    assert page.evaluate("currentSlideIndex") == 0
    scrolled = slides.evaluate("node => node.scrollTop")

    for name in ("大纲", "讲稿"):
        panel(page, name)
        body = page.locator(".editor-document-body")
        expect(body).to_have_attribute("aria-busy", "false")
        expect(body.locator(".ant-skeleton")).to_have_count(0)
        assert body.evaluate("node => node.scrollHeight > node.clientHeight + 100")
        footer = page.locator(".editor-document-footer")
        footer_box = footer.bounding_box()
        body.hover()
        page.mouse.wheel(0, 100000)
        page.wait_for_function(
            "() => {const node=document.querySelector('.editor-document-body');return node.scrollTop > 100 && node.scrollTop + node.clientHeight >= node.scrollHeight - 2}"
        )
        assert tabs.bounding_box() == tabs_box
        assert sidebar.bounding_box() == sidebar_box
        assert footer.bounding_box() == footer_box
        assert footer_box["y"] + footer_box["height"] <= size[1] + 1

    panel(page, "幻灯片")
    assert slides.evaluate("node => node.scrollTop") == pytest.approx(scrolled, abs=1)
    page.locator(".slide-thumbnail").last.click()
    assert page.evaluate("currentSlideIndex") == 11
    assert not state["writes"] and not state["document_writes"] and not state["errors"]
    assert page.evaluate(
        "document.documentElement.scrollHeight <= innerHeight + 1 && document.documentElement.scrollWidth <= innerWidth"
    )


def test_outline_drafts_follow_pages_tabs_and_save_without_artwork_requests(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    title.fill("更清楚的封面标题")
    page.get_by_role("textbox", name="大纲要点 1", exact=True).fill("修改后的核心目标")
    page.get_by_role("button", name="添加要点", exact=True).click()
    page.get_by_role("textbox", name="大纲要点 3", exact=True).fill("新增第三点")
    next_page(page)
    expect(title).to_have_value("实施计划")
    title.fill("第二页的草稿")
    panel(page, "讲稿")
    expect(page.get_by_text("当前页暂无讲稿", exact=True)).to_be_visible()
    panel(page, "大纲")
    expect(title).to_have_value("第二页的草稿")
    page.get_by_role("button", name="上一页", exact=True).click()
    expect(title).to_have_value("更清楚的封面标题")
    title.press("Control+s")
    expect(page.get_by_text("大纲已保存", exact=True)).to_be_visible()
    index, language, body = state["document_writes"][0]
    assert (index, language, body["kind"], body["slide_id"]) == (
        0,
        "zh",
        "outline",
        "stable-0",
    )
    assert body["outline"]["content_points"] == [
        "修改后的核心目标",
        "组织实施",
        "新增第三点",
    ]
    assert len(body["revision"]) == 64
    assert page.evaluate("projectOutline.slides[0].custom") == {"layout": "keep"}
    assert page.evaluate("slidesData[0].title") == "更清楚的封面标题"
    assert page.evaluate("slidesData[0].html_content") == HTML
    next_page(page)
    expect(title).to_have_value("第二页的草稿")
    assert state["writes"] == [] and state["errors"] == []


def test_thumbnail_list_can_be_scrolled_from_the_keyboard(ui_page):
    page, load = ui_page
    state = document_setup(page, load, slide_count=12)
    slides = page.get_by_role("region", name="幻灯片列表", exact=True)
    slides.focus()
    expect(slides).to_be_focused()
    slides.press("End")
    page.wait_for_function(
        "() => {const node=document.querySelector('.slides-container');return node.scrollTop > 100 && node.scrollTop + node.clientHeight >= node.scrollHeight - 2}"
    )
    end = slides.evaluate("node => node.scrollTop")
    slides.press("PageUp")
    page.wait_for_function(
        "end => document.querySelector('.slides-container').scrollTop < end - 100",
        arg=end,
    )
    assert page.evaluate("currentSlideIndex") == 0
    assert not state["writes"] and not state["document_writes"] and not state["errors"]


def test_speech_manual_creation_language_drafts_and_saving_fields(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "讲稿")
    page.get_by_role("button", name="编辑文稿", exact=True).click()
    content = page.get_by_role("textbox", name="讲稿正文", exact=True)
    expect(content).to_have_value(re.compile("介绍核心目标"))
    content.fill("中文修改草稿")
    page.get_by_role("combobox", name="讲稿语言", exact=True).click()
    page.get_by_text("English", exact=True).last.click()
    expect(page.get_by_text("当前页暂无讲稿", exact=True)).to_be_visible()
    page.get_by_role("button", name="撰写讲稿", exact=True).click()
    content.fill("English manual script")
    page.get_by_role("textbox", name="讲稿预计时长", exact=True).fill("3 minutes")
    page.get_by_role("textbox", name="演讲者备注", exact=True).fill(
        "Pause after introduction"
    )
    page.locator(".editor-document-footer").get_by_role(
        "button", name="保存讲稿", exact=True
    ).click()
    expect(page.get_by_text("讲稿已保存", exact=True)).to_be_visible()
    index, language, body = state["document_writes"][0]
    assert (index, language, body["kind"]) == (0, "en", "speech")
    assert body["speech"] == {
        "slide_title": "封面",
        "script_content": "English manual script",
        "estimated_duration": "3 minutes",
        "speaker_notes": "Pause after introduction",
    }
    page.get_by_role("combobox", name="讲稿语言", exact=True).click()
    page.get_by_text("中文", exact=True).last.click()
    expect(content).to_have_value("中文修改草稿")
    page.get_by_role("button", name="阅读文稿", exact=True).click()
    expect(page.locator(".editor-document-reading p").first).to_have_text(
        "中文修改草稿"
    )
    assert state["writes"] == [] and state["errors"] == []


@pytest.mark.parametrize("conflict", [False, True])
def test_failed_save_preserves_draft_and_reload_requires_explicit_discard(
    ui_page, conflict
):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    title.fill("保留失败草稿")
    state["conflict" if conflict else "document_fail"] = True
    page.locator(".editor-document-footer").get_by_role(
        "button", name="保存大纲", exact=True
    ).click()
    expect(page.get_by_text("暂时无法保存或加载", exact=True)).to_be_visible()
    expect(title).to_have_value("保留失败草稿")
    panel(page, "幻灯片")
    panel(page, "大纲")
    expect(title).to_have_value("保留失败草稿")
    page.get_by_role("button", name="重新加载文稿", exact=True).click()
    page.get_by_role("button", name="保留修改", exact=True).click()
    expect(title).to_have_value("保留失败草稿")
    state["conflict"] = state["document_fail"] = False
    page.get_by_role("button", name="重新加载文稿", exact=True).click()
    page.get_by_role("dialog").get_by_role(
        "button", name="重新加载", exact=True
    ).click()
    expect(title).to_have_value("封面")
    assert state["errors"] == []


def test_loading_error_retry_empty_editor_and_existing_generation_entry(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    state["document_fail"] = True
    panel(page, "讲稿")
    expect(page.get_by_role("button", name="重试加载", exact=True)).to_be_visible()
    state["document_fail"] = False
    page.get_by_role("button", name="重试加载", exact=True).click()
    expect(page.locator(".editor-document-reading h2")).to_have_text("封面")
    page.get_by_role("button", name="生成讲稿", exact=True).click()
    expect(page.locator(".editor-ant-dialog")).to_be_visible()
    assert state["document_writes"] == [] and state["writes"] == []
    assert state["errors"] == []


def test_empty_editor_document_tabs_are_safe(ui_page):
    page, load = ui_page
    state = document_setup(page, load, empty=True)
    panel(page, "大纲")
    expect(page.get_by_text("暂无幻灯片", exact=True).last).to_be_visible()
    expect(
        page.locator(".editor-document-footer").get_by_role(
            "button", name="保存大纲", exact=True
        )
    ).to_be_disabled()
    panel(page, "讲稿")
    expect(
        page.locator(".editor-document-footer").get_by_role(
            "button", name="保存讲稿", exact=True
        )
    ).to_be_disabled()
    assert state["document_reads"] == [] and state["errors"] == []


def test_toolbar_save_routes_to_current_document_and_return_to_canvas(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    save_button = page.locator(".editor-ant-toolbar").get_by_role(
        "button", name="保存大纲", exact=True
    )
    expect(save_button).to_be_disabled()
    title.fill("由工具栏保存")
    expect(save_button).to_be_enabled()
    save_button.click()
    expect(page.get_by_text("大纲已保存", exact=True)).to_be_visible()
    expect(save_button).to_be_disabled()
    assert len(state["document_writes"]) == 1 and not state["writes"]
    panel(page, "幻灯片")
    expect(
        page.locator(".editor-ant-toolbar").get_by_role(
            "button", name="保存", exact=True
        )
    ).to_be_enabled()
    assert state["errors"] == []


def test_dirty_warning_and_native_copy_identity_are_independent(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    title.fill("未保存草稿")
    assert page.evaluate(
        "() => {const e=new Event('beforeunload',{cancelable:true});dispatchEvent(e);return e.defaultPrevented}"
    )
    identity = page.evaluate(
        "() => {const original=slidesData[0];const copy=cloneSlideForInsert(original,1);return {source:original.slide_id,copy:copy.slide_id,html:copy.html_content}}"
    )
    assert identity["source"] != identity["copy"] and identity["html"] == HTML
    panel(page, "幻灯片")
    assert page.evaluate(
        "() => {const e=new Event('beforeunload',{cancelable:true});dispatchEvent(e);return e.defaultPrevented}"
    )
    assert not state["document_writes"] and not state["writes"] and not state["errors"]


def test_late_document_response_cannot_replace_newly_selected_page(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    held = []

    def delay(route):
        if not held and route.request.method == "GET":
            held.append(route)
        else:
            route.fallback()

    page.route("**/editor-documents/0?*", delay)
    panel(page, "大纲")
    expect(page.locator(".editor-document-body .ant-skeleton")).to_be_visible()
    next_page(page)
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("实施计划")
    held[0].fulfill(
        json={
            "success": True,
            "document": {
                "slide_index": 0,
                "slide_id": "stable-0",
                "language": "zh",
                "outline": {"title": "迟到的第一页响应", "slide_type": "title"},
                "script": None,
                "outline_revision": "a" * 64,
                "speech_revision": "b" * 64,
            },
        }
    )
    expect(title).to_have_value("实施计划")
    assert page.evaluate("currentSlideIndex") == 1
    assert not state["document_writes"] and not state["writes"] and not state["errors"]


def test_draft_survives_replacement_of_slide_objects_from_server_refresh(ui_page):
    page, load = ui_page
    state = document_setup(page, load)
    panel(page, "大纲")
    title = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(title).to_have_value("封面")
    title.fill("服务器刷新后保留的草稿")
    page.evaluate(
        "() => {slidesData=structuredClone(slidesData);window.slidesData=slidesData;refreshSidebar()}"
    )
    expect(title).to_have_value("服务器刷新后保留的草稿")
    panel(page, "讲稿")
    panel(page, "大纲")
    expect(title).to_have_value("服务器刷新后保留的草稿")
    assert not state["document_writes"] and not state["writes"] and not state["errors"]
