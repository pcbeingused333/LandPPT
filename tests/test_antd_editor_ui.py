"""Actual editor UI and native controllers, with isolated API responses."""

import json
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
HTML = '<html><body style="margin:0;width:1280px;height:720px;background:#fafafa;color:#111;font-family:Arial"><h1 style="font-size:48px;margin:80px">原始演示内容</h1><p style="margin:80px">页面样式与画布尺寸保持不变</p></body></html>'
SVG_HTML = '<html><body data-render-mode="svg" style="margin:0;width:1280px;height:720px"><svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect id="background" width="1280" height="720" fill="#f5f5f5"/><text id="heading" x="80" y="120" font-size="48" fill="#111">SVG 原始内容</text><rect id="card" x="80" y="220" width="600" height="300" fill="#dedede"/></svg></body></html>'
SCRIPTS = dict(
    success=True,
    scripts=[
        dict(
            slide_index=0,
            slide_title="封面",
            script_content="介绍核心目标与实施过程。" * 80,
            estimated_duration="2分钟",
            language="zh",
        )
    ],
    total_estimated_duration="2分钟",
)
IMAGE = dict(
    id="img-1",
    name="研发示意图",
    title="研发示意图",
    url="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='90'><rect width='160' height='90' fill='gray'/></svg>",
    size=1024,
    category="local_upload",
)


def setup(
    page,
    load,
    svg=False,
    restricted=True,
    package=False,
    native=False,
    empty=False,
    slide_count=2,
):
    state = dict(errors=[], reads=[], writes=[], fail=False)
    page.on("pageerror", lambda error: state["errors"].append(str(error)))
    slides = [
        dict(
            page_number=i + 1,
            title=title,
            render_mode="svg" if svg else "html",
            html_content=SVG_HTML if svg else HTML,
        )
        for i, title in enumerate(
            ["封面", "实施计划"] + [f"实施阶段 {i + 1}" for i in range(2, slide_count)]
        )
    ]
    if empty:
        slides = []
    outline = dict(
        title="研发协作计划",
        slides=[
            dict(
                page_number=i + 1,
                title=slide["title"],
                slide_type="title" if i == 0 else "content",
                content_points=["确认目标", "组织实施"],
                description="说明核心内容",
            )
            for i, slide in enumerate(slides)
        ],
    )
    project = dict(
        project_id="ui-editor",
        title="研发团队的协作与设计计划",
        topic="研发协作",
        scenario="general",
        status="completed",
        outline=outline,
        slides_data=slides,
        project_metadata=dict(render_mode="svg" if svg else "html"),
        requirements="保留所有关键事实",
    )

    def api(route):
        req = route.request
        path = urlsplit(req.url).path
        if req.resource_type == "document":
            route.fallback()
            return
        if req.method == "GET":
            state["reads"].append(path)
        else:
            state["writes"].append(
                (path, req.method, req.post_data_json if req.post_data else None)
            )
        result = dict(
            success=True,
            status="success",
            project=project,
            images=[IMAGE],
            pagination=dict(current_page=1, total_pages=1, total_count=1),
            templates=[],
            total_pages=1,
            run=None,
            enabled=False,
            notifications=[],
            unread_count=0,
        )
        code = 200
        if path.endswith("/template-package"):
            if package:
                result = dict(
                    pages=[
                        dict(
                            slide_index=0,
                            slide_id="slide-1",
                            revision=3,
                            component_id="cover-1",
                            content=dict(
                                title="模板包封面",
                                subtitle="",
                                blocks=[dict(heading="目标", body="保留核心内容")],
                                metrics=[],
                                takeaway="明确设计",
                                visual_briefs=[],
                            ),
                        )
                    ]
                )
            else:
                code, result = 404, dict(detail="当前项目未使用模板包")
        elif path.endswith("/layouts"):
            result = dict(
                components=[dict(id="cover-1", family="cover", description="封面版式")]
            )
        elif path.endswith("/selected-global-template") or path.endswith(
            "/free-template"
        ):
            result = dict(template=None)
        elif path.endswith("/share/generate"):
            result = dict(share_url="/share/ui-editor")
        elif path.endswith("/speech-scripts"):
            result = SCRIPTS
        elif path.endswith("/speech-script/generate"):
            result = dict(success=False, error="生成服务暂时不可用")
        elif state["fail"] and req.method != "GET":
            code, result = 503, dict(detail="保存服务暂时不可用")
        route.fulfill(status=code, json=result)

    page.route("**/api/**", api)
    load(
        "pages/project/project_slides_editor.html",
        path="/projects/ui-editor/edit",
        project=project,
        has_speech_scripts=True,
        narration_languages=["zh", "en"],
        standard_pptx_export_enabled=not restricted,
        narration_video_tools_enabled=not restricted,
        enable_auto_layout_repair=not restricted,
    )
    # Retired toolbar nodes are inert/hidden even without React; the native
    # preview remains the controller's visible initialization boundary.
    page.locator("#slideFrame" if native else ".editor-ant-toolbar").wait_for()
    return state


def open_scene(page, scene, native=False):
    expressions = {
        "outline": "showSlideOutline()",
        "optimize": "showAIOptimizeModal({title:'优化当前页面',currentInfo:'保留所有关键事实',suggestions:['简化内容','突出结论']})",
        "speech": "showSpeechScriptDialog()",
        "speech-preview": "showSpeechScriptPreview("
        + json.dumps(SCRIPTS, ensure_ascii=False)
        + ",false)",
        "template": "showChangeTemplateDialog()",
        "share": "showShareDialog()",
        "library": "showImageLibrary()",
        "gallery": "showImageGalleryDialog()",
        "image-preview": "showImagePreview(" + json.dumps(IMAGE) + ")",
        "image-confirm": "showAutoImageGenerateConfirmDialog()",
        "image-regenerate": "showImageRegenerateConfirmDialog()",
        "image-delete": "showImageDeleteConfirmDialog()",
        "diff": "showAgentDiff('@@ 页面改动 @@\\n-原内容\\n+新内容')",
        "chat": "openNativeChatDialog()",
        "svg": "openSvgPageEditor()",
    }
    page.evaluate("() => { " + expressions[scene] + "; }")
    selectors = {
        "outline": ".outline-modal",
        "optimize": ".ai-optimize-modal",
        "speech": ".modal",
        "speech-preview": ".modal",
        "template": ".tpl-dialog-overlay",
        "share": ".lp-share-modal",
        "library": "#imageLibraryOverlay",
        "gallery": ".modal",
        "image-preview": "#imagePreviewOverlay",
        "image-confirm": ".modal",
        "image-regenerate": ".modal",
        "image-delete": ".modal",
        "diff": ".agent-diff-modal",
        "chat": "#aiNativeChatDialog",
        "svg": "#svg-page-editor",
    }
    dialog = page.locator(selectors[scene] if native else ".editor-ant-dialog")
    expect(dialog).to_be_visible()
    return dialog


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("svg", [False, True])
def test_editor_workspace_geometry_and_preserved_frame(ui_page, width, height, svg):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, svg=svg)
    expect(page.get_by_role("navigation", name="创作阶段", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="保存", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert page.locator(".editor-container").bounding_box()["height"] <= height
    frame = page.locator("#slideFrame")
    box = frame.bounding_box()
    assert box["width"] > 0 and box["height"] > 0
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert box["y"] + box["height"] <= height + 1
    assert "1280px" in frame.get_attribute("srcdoc") and (
        "SVG 原始内容" if svg else "原始演示内容"
    ) in frame.get_attribute("srcdoc")
    action = page.get_by_role("button", name="保存", exact=True)
    assert action.bounding_box()["height"] >= (44 if width <= 700 else 32)
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize(
    "scene",
    [
        "outline",
        "optimize",
        "speech",
        "speech-preview",
        "template",
        "share",
        "library",
        "gallery",
        "image-preview",
        "image-confirm",
        "image-regenerate",
        "image-delete",
        "diff",
        "chat",
    ],
)
def test_editor_dialogs_are_bounded_and_close_through_native_lifecycle(
    ui_page, width, height, scene
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load)
    dialog = open_scene(page, scene)
    box = dialog.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    footer = dialog.locator(".ant-modal-footer")
    if footer.count():
        assert footer.bounding_box()["y"] + footer.bounding_box()["height"] <= height
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert not state["errors"]
    assert len(state["writes"]) == (1 if scene == "share" else 0)


def test_editor_outline_nested_optimization_and_reopen_keep_native_handlers(ui_page):
    page, load = ui_page
    state = setup(page, load)
    dialog = open_scene(page, "outline")
    page.get_by_role("textbox", name="标题：", exact=True).fill("保留编辑草稿")
    dialog.get_by_role("button", name="AI优化", exact=True).click()
    nested = page.locator(".editor-ant-dialog").last
    expect(nested).to_contain_text("优化需求")
    page.keyboard.press("Escape")
    expect(page.locator(".editor-ant-dialog")).to_have_count(1)
    expect(page.locator("#slideTitle")).to_have_value("保留编辑草稿")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    open_scene(page, "outline")
    expect(page.locator("#slideTitle")).to_have_value("封面")
    assert not state["writes"] and not state["errors"]


def test_editor_static_image_dialogs_restore_nodes_after_repeated_close(ui_page):
    page, load = ui_page
    state = setup(page, load)
    for _ in range(3):
        dialog = open_scene(page, "library")
        expect(page.locator("#imageLibraryGrid")).to_contain_text("研发示意图")
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        assert page.locator("#imageLibrarySearchInput").count() == 1
        assert page.locator("#confirmSelectionBtn").count() == 1
    assert not state["errors"]


def test_editor_cancelled_image_confirm_resolves_original_promise(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.evaluate(
        "() => { window.confirmResult='pending';showAutoImageGenerateConfirmDialog().then(value=>window.confirmResult=value); }"
    )
    dialog = page.locator(".editor-ant-dialog")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    page.wait_for_function("window.confirmResult===false")
    assert not state["writes"] and not state["errors"]


def test_editor_save_source_and_failed_save_keep_existing_payload(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.get_by_role("toolbar", name="幻灯片编辑工具").get_by_title("代码", exact=True).click()
    source = HTML.replace("原始演示内容", "保存后的内容")
    page.locator("#codeEditor").fill(source)
    state["fail"] = True
    page.get_by_role("button", name="保存", exact=True).click()
    expect(page.locator(".ant-message-notice")).to_contain_text("保存失败")
    expect(page.locator("#codeEditor")).to_have_value(source)
    state["fail"] = False
    page.get_by_role("button", name="保存", exact=True).click()
    expect(page.locator(".ant-message-notice").last).to_contain_text("已保存")
    assert any(
        body and body.get("html_content") == source for _, _, body in state["writes"]
    )
    assert not state["errors"]


@pytest.mark.parametrize("restricted", [False, True])
def test_editor_permission_dependent_actions_keep_visibility(ui_page, restricted):
    page, load = ui_page
    state = setup(page, load, restricted=restricted)
    page.get_by_role("button", name="导出", exact=True).click()
    assert page.get_by_role("radio", name="标准导出 PPTX", exact=True).count() == (
        0 if restricted else 1
    )
    page.keyboard.press("Escape")
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(page.get_by_role("region", name="AI 编辑助手", exact=True)).to_be_visible()
    assert page.get_by_role("button", name="修复排版", exact=True).count() == (
        0 if restricted else 1
    )
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("width,height", SIZES)
def test_editor_svg_canvas_bounded_with_original_dirty_close(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, svg=True)
    page.get_by_role("button", name="编辑 SVG", exact=True).click()
    editor = page.locator("#svg-page-editor")
    expect(editor).to_be_visible()
    box = editor.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert box["y"] + box["height"] <= height + 1
    page.frame_locator("#svg-page-editor iframe").locator("#heading").click()
    expect(editor.locator("[data-inspector]")).to_be_visible()
    bounds = editor.bounding_box()
    for action in ["[data-save]", "[data-close]", "[data-zoom='fit']"]:
        button = editor.locator(action)
        box = button.bounding_box()
        assert (
            box["x"] >= bounds["x"]
            and box["x"] + box["width"] <= bounds["x"] + bounds["width"] + 1
        )
        assert box["y"] + box["height"] <= height
    editor.locator("[data-close]").click()
    expect(editor).not_to_be_visible()
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("width,height", SIZES)
def test_editor_package_content_footer_and_original_dialog_close(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, package=True)
    page.get_by_role("button", name="内容与版式", exact=True).click()
    dialog = page.locator(".editor-ant-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("button", name="保存内容", exact=True)).to_be_visible()
    footer = dialog.locator(".ant-modal-footer")
    expect(footer).to_be_visible()
    box = dialog.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert box["y"] + box["height"] <= height + 1
    assert footer.bounding_box()["y"] + footer.bounding_box()["height"] <= height
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert not state["writes"] and not state["errors"]


def test_editor_resize_recomputes_canvas_without_rewriting_srcdoc(ui_page):
    page, load = ui_page
    state = setup(page, load)
    initial = page.locator("#slideFrame").get_attribute("srcdoc")
    for width, height in [(390, 844), (844, 390), (1440, 900)]:
        page.set_viewport_size(dict(width=width, height=height))
        page.wait_for_timeout(300)
        box = page.locator("#slideFrame").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
        assert page.locator("#slideFrame").get_attribute("srcdoc") == initial
    assert not state["errors"] and not state["writes"]


def test_editor_export_progress_title_and_no_unintended_cancel(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.evaluate("() => { showExportOverlay(); }")
    dialog = page.locator(".editor-ant-dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("正在导出 PPTX")
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    page.evaluate(
        "() => { document.getElementById('exportTitle').textContent='正在打包文件'; }"
    )
    expect(dialog.locator(".ant-modal-title")).to_have_text("正在打包文件")
    page.evaluate("() => { hideExportOverlay(); }")
    expect(dialog).not_to_be_visible()
    page.evaluate("() => { showExportOverlay(); }")
    expect(dialog).to_be_visible()
    page.evaluate("() => { hideExportOverlay(); }")
    assert not state["errors"] and not state["writes"]


def test_editor_saving_locks_duplicate_clicks(ui_page):
    page, load = ui_page
    state = setup(page, load)
    held = []
    page.route("**/slides/*/save", lambda route: held.append(route))
    action = page.get_by_role("button", name="保存", exact=True)
    action.dblclick()
    page.wait_for_timeout(100)
    assert len(held) == 1
    held[0].fulfill(json=dict(success=True))
    page.wait_for_timeout(100)
    assert len(held) == 1
    expect(action).not_to_have_class(re.compile("ant-btn-loading"))
    assert not state["errors"]


def test_editor_native_modal_keyboard_trap_and_focus_restore(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    page.get_by_role("button", name="查看当前页大纲", exact=True).click()
    dialog = page.locator(".editor-ant-dialog")
    expect(dialog).to_be_visible()
    last = dialog.locator(".ant-modal-footer button").last
    last.focus()
    page.keyboard.press("Tab")
    assert dialog.evaluate("e=>e.contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert not state["errors"]


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_editor_svg_dirty_discard_stays_inside_ant_frame(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, svg=True)
    page.get_by_role("button", name="编辑 SVG", exact=True).click()
    editor = page.locator("#svg-page-editor")
    frame = page.frame_locator("#svg-page-editor iframe")
    frame.locator("#heading").click()
    editor.locator("[data-prop='content']").fill("已修改的 SVG 标题")
    expect(frame.locator("#heading")).to_contain_text("已修改")
    editor.locator("[data-close]").click()
    expect(editor.locator("[data-discard]")).to_be_visible()
    editor.locator("[data-keep]").click()
    expect(editor).to_be_visible()
    editor.locator("[data-close]").click()
    editor.locator("[data-discard]").click()
    expect(editor).not_to_be_visible()
    assert "SVG 原始内容" in page.locator("#slideFrame").get_attribute("srcdoc")
    assert not state["writes"] and not state["errors"]


def test_editor_empty_state_has_clear_counter_and_disabled_actions(ui_page):
    page, load = ui_page
    state = setup(page, load, empty=True)
    expect(page.locator(".editor-ant-title")).to_contain_text("暂无幻灯片")
    for name in ["保存", "放映", "AI 编辑", "导出"]:
        expect(page.get_by_role("button", name=name, exact=True)).to_be_disabled()
    assert not state["writes"] and not state["errors"]


def test_editor_ant_select_keeps_visible_value_and_primary_action_light(ui_page):
    page, load = ui_page
    state = setup(page, load)
    original = page.locator("#slideFrame").get_attribute("srcdoc")
    dialog = open_scene(page, "outline")
    field = dialog.get_by_role("combobox", name="类型：", exact=True)
    expect(dialog.locator(".ant-select-content")).to_contain_text("标题页")
    assert (
        field.evaluate("node => getComputedStyle(node).backgroundColor")
        == "rgba(0, 0, 0, 0)"
    )
    assert field.evaluate("node => getComputedStyle(node).borderTopWidth") == "0px"
    save = dialog.get_by_role("button", name="保存大纲", exact=True)
    assert (
        save.evaluate("node => getComputedStyle(node).backgroundColor")
        == "rgb(245, 245, 245)"
    )
    field.click()
    page.locator(".ant-select-dropdown .ant-select-item-option-content").filter(
        has_text="内容页"
    ).click()
    expect(page.locator("#slideType")).to_have_value("content")
    expect(dialog.locator(".ant-select-content")).to_contain_text("内容页")
    field.click()
    field.press("Escape")
    expect(dialog).to_be_visible()
    expect(field).to_have_attribute("aria-expanded", "false")
    assert page.locator("#slideFrame").get_attribute("srcdoc") == original
    assert not state["writes"] and not state["errors"]
