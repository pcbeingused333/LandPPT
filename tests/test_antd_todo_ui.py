"""Built task board: multipart requirements, Ant outline and original stream."""

import json
import re
from email.parser import BytesParser
from email.policy import default
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
OUTLINE = dict(
    title="研发协作计划",
    slides=[
        dict(
            page_number=1,
            title="研发协作",
            slide_type="title",
            content_points=["组织需求", "确认设计"],
        ),
        dict(
            page_number=2,
            title="实施步骤",
            slide_type="content",
            content_points=["先内容，后版式"],
        ),
    ],
)


def open_json(page):
    page.get_by_role("button", name="编辑 JSON", exact=True).click()
    return page.get_by_role("dialog", name="编辑 PPT 大纲", exact=True)


def assert_modal_bounds(page, dialog):
    box = dialog.bounding_box()
    size = page.viewport_size
    assert box["x"] >= 0 and box["x"] + box["width"] <= size["width"]
    assert box["y"] >= 0 and box["y"] + box["height"] <= size["height"]
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth")
    action = dialog.get_by_role("button", name="保存修改", exact=True)
    assert action.bounding_box()["height"] >= (44 if size["width"] <= 600 else 32)
    action.focus()
    page.keyboard.press("Tab")
    assert dialog.evaluate("e=>e.contains(document.activeElement)")


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("editor", ["json", "slide"])
def test_outline_editor_geometry_and_keyboard_focus(ui_page, width, height, editor):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, scene="outline")
    if editor == "json":
        dialog = open_json(page)
    else:
        page.get_by_role("button", name="编辑第 1 页", exact=True).click()
        dialog = page.get_by_role("dialog", name="编辑第 1 页", exact=True)
    assert_modal_bounds(page, dialog)
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(
        page.get_by_role(
            "button",
            name="编辑 JSON" if editor == "json" else "编辑第 1 页",
            exact=True,
        )
    ).to_be_focused()
    assert not state["writes"] and not state["errors"]


def test_outline_json_invalid_save_failure_retry_and_cancel(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline")
    dialog = open_json(page)
    editor = dialog.get_by_role("textbox", name="大纲 JSON", exact=True)
    editor.fill('{"slides":[]}')
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("至少一页")
    assert not state["writes"]
    changed = {**OUTLINE, "title": "编辑后的大纲", "extra_root": {"keep": 7}}
    editor.fill(json.dumps(changed, ensure_ascii=False))
    state["fail"] = True
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("保存服务暂时不可用")
    expect(editor).to_have_value(json.dumps(changed, ensure_ascii=False))
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    state["fail"] = False
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator(".todo-outline-summary")).to_contain_text("编辑后的大纲")
    assert json.loads(state["payloads"][-1][1]["outline_content"]) == changed
    before = len(state["writes"])
    dialog = open_json(page)
    dialog.get_by_role("textbox", name="大纲 JSON").fill("discard this draft")
    dialog.get_by_role("button", name="取消", exact=True).click()
    assert len(state["writes"]) == before
    assert not state["errors"]


def test_outline_single_slide_preserves_hidden_fields_and_optional_deletion(ui_page):
    page, load = ui_page
    original = json.loads(json.dumps(OUTLINE))
    original["metadata"] = dict(language="en", other="retained")
    original["slides"][0].update(
        subtitle="旧副标题",
        description="旧描述",
        content="保留正文",
        chart_config={"type": "radar"},
        slide_type="custom-kind",
        backend_key=9,
    )
    state = setup(page, load, scene="outline", initial_outline=original)
    page.get_by_role("button", name="编辑第 1 页", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑第 1 页", exact=True)
    expect(dialog.locator(".ant-select")).to_contain_text("custom-kind")
    dialog.get_by_role("textbox", name="页面标题", exact=True).fill("更新封面")
    dialog.get_by_role("textbox", name="副标题", exact=True).fill("")
    dialog.get_by_role("textbox", name="页面描述", exact=True).fill("")
    dialog.get_by_role("button", name="删除要点 1", exact=True).click()
    dialog.get_by_role("button", name="删除要点 1", exact=True).click()
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("至少需要一个内容要点")
    assert not state["writes"]
    dialog.get_by_role("button", name="添加要点", exact=True).click()
    dialog.get_by_role("textbox", name="要点 1", exact=True).fill("新要点")
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    expect(dialog).not_to_be_visible()
    saved = json.loads(state["payloads"][-1][1]["outline_content"])
    assert saved["metadata"] == original["metadata"]
    assert saved["slides"][1] == original["slides"][1]
    slide = saved["slides"][0]
    assert slide["content"] == "保留正文" and slide["chart_config"] == {"type": "radar"}
    assert slide["backend_key"] == 9 and slide["type"] == "custom-kind"
    assert "subtitle" not in slide and "description" not in slide
    assert slide["content_points"] == ["新要点"]
    assert not state["errors"]


@pytest.mark.parametrize("single", [False, True])
def test_outline_ai_draft_payload_errors_and_explicit_save(ui_page, single):
    page, load = ui_page
    original = {
        **OUTLINE,
        "metadata": dict(
            language="ja",
            target_audience="自定义",
            custom_audience="研发主管",
            scenario="keynote",
        ),
    }
    state = setup(page, load, scene="outline", initial_outline=original)
    if single:
        page.get_by_role("button", name="编辑第 1 页", exact=True).click()
        editor = page.get_by_role("dialog", name="编辑第 1 页", exact=True)
        editor.get_by_role("textbox", name="页面标题", exact=True).fill(
            "未保存的封面草稿"
        )
    else:
        editor = open_json(page)
    editor.get_by_role("button", name="AI 优化", exact=True).click()
    dialog = page.get_by_role("dialog", name="AI 优化", exact=True)
    dialog.get_by_role("button", name="开始优化", exact=True).click()
    expect(dialog).to_contain_text("请输入优化要求")
    assert not state["writes"]
    dialog.get_by_role("textbox", name="优化要求", exact=True).fill("突出关键结论")
    dialog.get_by_role("button", name="开始优化", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("AI 服务暂时不可用")
    payload = state["payloads"][-1][1]
    assert (
        payload["language"] == "ja"
        and payload["project_info"]["target_audience"] == "研发主管"
    )
    assert payload["optimization_type"] == ("single" if single else "full")
    if single:
        assert payload["slide_index"] == 0
        assert (
            json.loads(payload["outline_content"])["slides"][0]["title"]
            == "未保存的封面草稿"
        )
    optimized = (
        {**OUTLINE["slides"][0], "title": "优化后的封面"}
        if single
        else {**original, "title": "优化后的大纲"}
    )
    state["optimize_result"] = dict(success=True, optimized_content="invalid json")
    dialog.get_by_role("button", name="开始优化", exact=True).click()
    expect(dialog.get_by_role("alert")).to_be_visible()
    expect(dialog).to_be_visible()
    state["optimize_result"] = dict(
        success=True, optimized_content=json.dumps(optimized)
    )
    dialog.get_by_role("button", name="开始优化", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert not any(path.endswith("/update-outline") for path, _ in state["writes"])
    expect(editor.get_by_role("button", name="AI 优化", exact=True)).to_be_focused()
    editor.get_by_role("button", name="保存修改", exact=True).click()
    expect(editor).not_to_be_visible()
    saved = json.loads(state["payloads"][-1][1]["outline_content"])
    assert (
        saved["slides"][0]["title"] == optimized["title"]
        if single
        else saved["title"] == optimized["title"]
    )
    assert not state["errors"]


def test_outline_export_view_detail_and_untrusted_text(ui_page):
    page, load = ui_page
    original = json.loads(json.dumps(OUTLINE))
    original["slides"][0][
        "title"
    ] = '<img src=x onerror="window.outlineInjection=true">'
    original["slides"][0]["content_points"].append("多行\n说明")
    state = setup(page, load, scene="outline", initial_outline=original)
    expect(page.locator(".todo-outline-grid")).to_contain_text(
        original["slides"][0]["title"]
    )
    assert page.locator(".todo-outline-grid img").count() == 0
    assert not page.evaluate("window.outlineInjection || false")
    page.get_by_role("button", name="详细视图", exact=True).click()
    expect(page.locator(".todo-outline-grid")).to_contain_text("多行")
    page.get_by_role("button", name="查看第 1 页", exact=True).click()
    dialog = page.get_by_role("dialog", name="第 1 页详情", exact=True)
    expect(dialog).to_contain_text("确认设计")
    dialog.get_by_role("button", name="关闭", exact=True).last.click()
    page.get_by_role("tab", name=re.compile("JSON$")).click()
    expect(page.locator(".todo-outline-json")).to_contain_text("研发协作计划")
    with page.expect_download() as pending_download:
        page.get_by_role("button", name="导出大纲 JSON", exact=True).click()
    assert (
        json.loads(open(pending_download.value.path(), encoding="utf-8").read())
        == original
    )
    assert not state["writes"] and not state["errors"]


def test_outline_regenerate_stream_error_retry_and_single_run_guard(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline")
    page.get_by_role("button", name="重新生成", exact=True).click()
    dialog = page.get_by_role("dialog", name="重新生成大纲", exact=True)
    dialog.get_by_role("button", name="取消", exact=True).click()
    assert not state["writes"]
    page.get_by_role("button", name="重新生成", exact=True).click()
    dialog.get_by_role("textbox", name="额外要求", exact=True).fill("增加协作实例")
    dialog.get_by_role("button", name="重新生成", exact=True).dblclick()
    page.wait_for_function("outlineStreams.length===1")
    assert sum(path.endswith("/regenerate-outline") for path, _ in state["writes"]) == 1
    assert next(
        payload
        for path, payload in state["payloads"]
        if path.endswith("/regenerate-outline")
    ) == {"custom_requirements": "增加协作实例"}
    expect(page.get_by_role("button", name="编辑 JSON", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="重新生成", exact=True)).to_be_disabled()
    page.evaluate("sendOutline({content:'正在组织新的章节'})")
    expect(page.get_by_label("大纲实时输出", exact=True)).to_contain_text(
        "正在组织新的章节"
    )
    page.evaluate("sendOutline({error:'模型服务暂时不可用 <script>unsafe</script>'})")
    expect(page.locator(".todo-outline-ant").get_by_role("alert")).to_contain_text(
        "模型服务暂时不可用"
    )
    expect(page.get_by_role("button", name="重新生成", exact=True)).to_be_enabled()
    page.get_by_role("button", name="重新生成", exact=True).click()
    dialog.get_by_role("button", name="重新生成", exact=True).click()
    page.wait_for_function("outlineStreams.length===2")
    page.evaluate(
        "outline=>{sendOutline({outline});sendOutline({done:true});}", OUTLINE
    )
    expect(page.locator(".todo-outline-grid")).to_contain_text("实施步骤")
    expect(page.get_by_role("button", name="编辑 JSON", exact=True)).to_be_enabled()
    assert not state["errors"]


def test_outline_start_navigation_uses_existing_confirmation(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline", start_stage=True)
    action = page.get_by_role("button", name="开始生成 PPT", exact=True)
    action.click()
    dialog = page.get_by_role("dialog", name="操作确认", exact=True)
    expect(dialog).to_contain_text("模板选择页面")
    dialog.get_by_role("button", name="取消", exact=True).click()
    assert not state["writes"]
    action.click()
    dialog.get_by_role("button", name="确认", exact=True).click()
    page.wait_for_url("**/template-selection")
    assert not state["writes"]


@pytest.mark.parametrize("width,height", SIZES)
def test_outline_ai_modal_geometry_and_focus_return(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, scene="outline")
    editor = open_json(page)
    editor.get_by_role("button", name="AI 优化", exact=True).click()
    dialog = page.get_by_role("dialog", name="AI 优化", exact=True)
    box = dialog.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    dialog.get_by_role("button", name="开始优化", exact=True).focus()
    page.keyboard.press("Tab")
    assert dialog.evaluate("e=>e.contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(editor.get_by_role("button", name="AI 优化", exact=True)).to_be_focused()
    assert not state["writes"] and not state["errors"]


def test_outline_slide_editor_does_not_reuse_optional_fields(ui_page):
    page, load = ui_page
    original = json.loads(json.dumps(OUTLINE))
    original["slides"][0].update(subtitle="只属于第一页", description="第一页描述")
    state = setup(page, load, scene="outline", initial_outline=original)
    page.get_by_role("button", name="编辑第 1 页", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑第 1 页", exact=True)
    dialog.get_by_role("button", name="取消", exact=True).click()
    page.get_by_role("button", name="编辑第 2 页", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑第 2 页", exact=True)
    expect(dialog.get_by_role("textbox", name="副标题", exact=True)).to_have_value("")
    expect(dialog.get_by_role("textbox", name="页面描述", exact=True)).to_have_value("")
    assert not state["writes"]


def test_outline_save_and_ai_disable_actions_while_waiting(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline")
    held = []
    page.route("**/update-outline", lambda route: held.append(route))
    dialog = open_json(page)
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    page.wait_for_timeout(100)
    assert len(held) == 1
    expect(dialog.get_by_role("button", name="取消", exact=True)).to_be_disabled()
    expect(dialog.get_by_role("button", name="AI 优化", exact=True)).to_be_disabled()
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    held[0].fulfill(json=dict(status="success"))
    expect(dialog).not_to_be_visible()
    held.clear()
    page.route("**/optimize-outline", lambda route: held.append(route))
    editor = open_json(page)
    editor.get_by_role("button", name="AI 优化", exact=True).click()
    dialog = page.get_by_role("dialog", name="AI 优化", exact=True)
    dialog.get_by_role("textbox", name="优化要求", exact=True).fill("突出重点")
    dialog.get_by_role("button", name="开始优化", exact=True).click()
    page.wait_for_timeout(100)
    assert len(held) == 1
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("button", name="取消", exact=True)).to_be_disabled()
    expect(editor.get_by_role("button", name="保存修改", exact=True)).to_be_disabled()
    held[0].fulfill(json=dict(success=True, optimized_content=json.dumps(OUTLINE)))
    expect(dialog).not_to_be_visible()
    expect(editor.get_by_role("button", name="保存修改", exact=True)).to_be_enabled()
    assert not state["errors"]


def test_outline_stream_scroll_preserves_reader_position_and_jump_action(ui_page):
    page, load = ui_page
    state = setup(page, load)
    fill(page)
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    page.wait_for_function("outlineStreams.length===1")
    page.evaluate(
        "sendOutline({content:Array.from({length:100},(_,i)=>'章节 '+i+'：组织内容与设计流程。').join('\\n')})"
    )
    preview = page.get_by_label("大纲实时输出", exact=True)
    expect(preview).to_contain_text("章节 99")
    preview.hover()
    page.mouse.wheel(0, -140)
    action = page.get_by_role("button", name="回到最新", exact=True)
    expect(action).to_be_visible()
    top = preview.evaluate("e=>e.scrollTop")
    page.evaluate("sendOutline({content:'\\n新回复：保留当前阅读位置'})")
    expect(preview).to_contain_text("保留当前阅读位置")
    assert abs(preview.evaluate("e=>e.scrollTop") - top) < 2
    action.click()
    expect(action).not_to_be_visible()
    assert preview.evaluate("e=>e.scrollHeight-e.scrollTop-e.clientHeight") <= 28
    assert not state["errors"]


def test_outline_rejects_invalid_point_shape_without_saving(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline")
    dialog = open_json(page)
    invalid = json.loads(json.dumps(OUTLINE))
    invalid["slides"][0]["content_points"] = "a string is not a points array"
    dialog.get_by_role("textbox", name="大纲 JSON", exact=True).fill(
        json.dumps(invalid)
    )
    dialog.get_by_role("button", name="保存修改", exact=True).click()
    expect(dialog.get_by_role("alert")).to_contain_text("content_points 必须是数组")
    assert not state["writes"] and not state["errors"]


def test_outline_failed_regeneration_keeps_extra_requirements(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline")
    state["regenerate_fail"] = True
    page.get_by_role("button", name="重新生成", exact=True).click()
    dialog = page.get_by_role("dialog", name="重新生成大纲", exact=True)
    dialog.get_by_role("textbox", name="额外要求", exact=True).fill(
        "增加协作实例，保留技术重点"
    )
    dialog.get_by_role("button", name="重新生成", exact=True).click()
    expect(page.locator(".todo-outline-ant").get_by_role("alert")).to_contain_text(
        "重新生成服务暂时不可用"
    )
    assert page.evaluate("outlineStreams.length") == 0
    page.get_by_role("button", name="重新生成", exact=True).click()
    expect(dialog.get_by_role("textbox", name="额外要求", exact=True)).to_have_value(
        "增加协作实例，保留技术重点"
    )
    state["regenerate_fail"] = False
    dialog.get_by_role("button", name="重新生成", exact=True).click()
    page.wait_for_function("outlineStreams.length===1")
    assert not state["errors"]


def multipart(request):
    raw = request.post_data_buffer
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + raw
    )
    fields, files = {}, []
    for part in message.iter_parts():
        if part.get_filename():
            files.append((part.get_filename(), part.get_payload(decode=True)))
        else:
            fields[part.get_param("name", header="content-disposition")] = (
                part.get_payload(decode=True).decode()
            )
    return fields, files


def setup(
    page,
    load,
    scene="pending",
    active=False,
    count_title=False,
    start_stage=False,
    initial_outline=None,
    stage_status=None,
    has_output=False,
    ppt_stage_status="pending",
):
    page.add_init_script(
        """window.outlineStreams=[];window.outlineRequests=[];window.outlineCancels=0;const originalFetch=window.fetch;window.fetch=(url,...args)=>{if(!String(url).includes('/outline-stream'))return originalFetch(url,...args);outlineRequests.push({url:String(url),signal:args[0]?.signal});return Promise.resolve(new Response(new ReadableStream({start(controller){outlineStreams.push(controller);},cancel(){outlineCancels++;}}),{headers:{'Content-Type':'text/event-stream'}}));};window.sendOutline=data=>outlineStreams.at(-1).enqueue(new TextEncoder().encode('data: '+JSON.stringify(data)+'\\n\\n'));"""
    )
    state = dict(
        reads=[],
        writes=[],
        fail=False,
        errors=[],
        fields=None,
        files=[],
        package_fail=False,
        run=None,
        payloads=[],
        optimize_result=None,
        regenerate_fail=False,
    )
    page.on("pageerror", lambda error: state["errors"].append(str(error)))
    if active:
        state["run"] = dict(
            task_status="running",
            status="running",
            topic="研发协作",
            overall_progress=42,
            stages=[
                dict(
                    id="outline",
                    name="生成大纲",
                    status="running",
                    message="正在整理资料",
                ),
                dict(id="video", name="导出视频", status="skipped"),
            ],
        )

    def api(route):
        req = route.request
        path = urlsplit(req.url).path
        if req.resource_type == "document":
            route.fallback()
            return
        (state["reads"] if req.method == "GET" else state["writes"]).append(
            (path, req.method)
        )
        code, result = 200, dict(
            status="success", project=dict(outline=OUTLINE), todo_board=dict(stages=[])
        )
        if req.method != "GET" and "application/json" in req.headers.get(
            "content-type", ""
        ):
            state["payloads"].append((path, req.post_data_json))
        if path.endswith("/confirm-requirements"):
            state["fields"], state["files"] = multipart(req)
            if state["fail"]:
                code, result = 503, dict(detail="需求保存服务暂时不可用")
        elif path.endswith("/unattended/status"):
            result = dict(run=state["run"])
        elif path.endswith("/update-outline") and state["fail"]:
            code, result = 503, dict(detail="大纲保存服务暂时不可用")
        elif path.endswith("/optimize-outline"):
            result = state["optimize_result"] or dict(
                success=False, error="AI 服务暂时不可用"
            )
        elif path.endswith("/regenerate-outline"):
            result = (
                dict(error="重新生成服务暂时不可用")
                if state["regenerate_fail"]
                else dict(status="success", defer_generation=True)
            )
        elif path.endswith("/unattended/cancel") and state["fail"]:
            code, result = 503, dict(detail="暂时无法停止任务")
        elif path.endswith("/packages"):
            if state["package_fail"]:
                code, result = 503, dict(detail="模板包目录暂时不可用")
            else:
                result = dict(
                    packages=[
                        dict(
                            id=7,
                            template_name="研发报告",
                            version=2,
                            status="published",
                        ),
                        dict(
                            id=8, template_name="未发布设计", version=3, status="draft"
                        ),
                    ]
                )
        route.fulfill(status=code, json=result)

    page.route("**/api/**", api)
    page.route("**/projects/ui-todo/**", api)
    project = dict(
        project_id="ui-todo",
        title="研发协作计划",
        topic="研发",
        outline=(
            (initial_outline if initial_outline is not None else OUTLINE)
            if scene == "outline"
            else None
        ),
        slides_data=[{"html_content": "Saved page"}] if has_output else [],
        slides_html=None,
        confirmed_requirements={} if scene == "pending" else dict(topic="研发"),
        project_metadata=dict(render_mode="html", generation_mode="freeform"),
    )
    stages = [
        dict(
            id="requirements_confirmation",
            status="pending" if scene == "pending" else "completed",
        ),
        dict(
            id="outline_generation",
            status=stage_status or ("completed" if scene == "outline" else "pending"),
        ),
    ]
    if start_stage:
        stages.append(dict(id="ppt_creation", status=ppt_stage_status))
    title = "研发与设计团队的跨部门协作" * 20 if count_title else project["title"]
    load(
        "pages/project/todo_board.html",
        path="/projects/ui-todo/todo",
        project=project,
        todo_board=dict(task_id="ui-todo", title=title, stages=stages),
        unattended_active=active,
    )
    page.get_by_role("heading", name=title, level=1, exact=True).wait_for()
    return state


def choose(page, name, value):
    page.get_by_role("combobox", name=name, exact=True).click()
    page.locator(".ant-select-dropdown:visible .ant-select-item-option-content").filter(
        has_text=re.compile("^" + re.escape(value) + "$")
    ).click()


def fill(page):
    choose(page, "目标受众", "技术团队")


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("scene", ["pending", "outline", "active", "failure"])
def test_task_board_geometry_first_screen_action_and_native_outline(
    ui_page, width, height, scene
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(
        page,
        load,
        scene="outline" if scene == "outline" else "pending",
        active=scene == "active",
    )
    if scene == "failure":
        state["fail"] = True
        fill(page)
        page.get_by_role("button", name="开始生成大纲", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("需求保存服务暂时不可用")
    if scene in ["pending", "failure"]:
        action = page.get_by_role("button", name="开始生成大纲", exact=True)
    elif scene == "active":
        action = page.get_by_role("button", name="停止无人值守任务", exact=True)
        assert page.get_by_role("button", name="开始生成大纲", exact=True).count() == 0
        assert page.evaluate("outlineStreams.length") == 0
        expect(page.locator(".unattended-ant-topic")).to_contain_text("正在生成大纲")
    else:
        action = page.get_by_role("link", name="快速模式设置", exact=True)
        expect(page.get_by_role("region", name="PPT 大纲工作区")).to_be_visible()
        expect(page.locator(".todo-outline-grid")).to_contain_text("研发协作")
        assert page.evaluate("outlineStreams.length") == 0
        assert (
            page.locator(
                "#todoLegacyHost, #workspace-body, .todo-ant-native-slot"
            ).count()
            == 0
        )
    expect(action).to_be_visible()
    box = action.bounding_box()
    assert box["y"] + box["height"] <= height
    assert box["height"] >= (44 if width <= 600 else 32)
    assert action.evaluate(
        "e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not state["errors"]


def test_requirements_post_once_and_then_start_one_native_stream(ui_page):
    page, load = ui_page
    state = setup(page, load)
    fill(page)
    page.get_by_role("checkbox", name="页码 / Footer").uncheck()
    page.get_by_role("button", name="开始生成大纲", exact=True).dblclick()
    page.wait_for_function("outlineStreams.length===1")
    assert state["writes"] == [("/projects/ui-todo/confirm-requirements", "POST")]
    assert state["fields"]["audience_type"] == "技术团队"
    assert state["fields"]["include_page_numbers"] == "false"
    assert state["fields"]["include_transition_pages"] == "false"
    assert state["fields"]["generation_mode"] == "freeform"
    assert state["fields"]["package_version_id"] == "0"
    assert state["fields"]["content_source"] == "manual"
    page.evaluate("sendOutline({content:'正在组织章节与要点'})")
    expect(page.locator("[data-outline-stream-preview]:visible").first).to_contain_text(
        "正在组织章节与要点"
    )
    page.evaluate(
        "outline=>{sendOutline({outline});sendOutline({done:true});}", OUTLINE
    )
    expect(page.locator(".todo-outline-grid")).to_contain_text("实施步骤")
    assert page.locator('form[name="todo-requirements"]').count() == 0
    assert not state["errors"]


def test_failed_requirements_keep_custom_fields_and_do_not_start_stream(ui_page):
    page, load = ui_page
    state = setup(page, load)
    choose(page, "目标受众", "自定义受众")
    page.get_by_role("textbox", name="自定义受众", exact=True).fill("研发负责人")
    choose(page, "演示风格", "自定义风格")
    page.get_by_role("textbox", name="自定义风格描述").fill("黑白极简，保留核心数据")
    state["fail"] = True
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("需求保存服务暂时不可用")
    expect(page.get_by_role("textbox", name="自定义受众", exact=True)).to_have_value(
        "研发负责人"
    )
    expect(page.get_by_role("textbox", name="自定义风格描述")).to_have_value(
        "黑白极简，保留核心数据"
    )
    assert page.evaluate("outlineStreams.length") == 0
    state["fail"] = False
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    page.wait_for_function("outlineStreams.length===1")
    assert state["fields"]["custom_audience"] == "研发负责人"
    assert state["fields"]["custom_style_prompt"] == "黑白极简，保留核心数据"


def test_file_upload_validation_and_source_switch_preserve_selected_files(ui_page):
    page, load = ui_page
    state = setup(page, load)
    fill(page)
    page.get_by_role("tab", name=re.compile("上传文件$")).click()
    page.locator('input[type="file"]').set_input_files(
        [
            dict(name="notes.txt", mimeType="text/plain", buffer=b"research notes"),
            dict(
                name="unsafe.exe",
                mimeType="application/octet-stream",
                buffer=b"blocked",
            ),
        ]
    )
    expect(page.get_by_role("alert")).to_contain_text("不支持的文件类型：unsafe.exe")
    expect(page.get_by_role("button", name="移除文件 notes.txt")).to_be_visible()
    page.get_by_role("tab", name=re.compile("网页链接$")).click()
    page.get_by_role("textbox", name="内容链接").fill("example.com/article")
    page.get_by_role("tab", name=re.compile("上传文件$")).click()
    page.get_by_role("textbox", name="主题", exact=True).fill("")
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    page.wait_for_function("outlineStreams.length===1")
    assert state["files"] == [("notes.txt", b"research notes")]
    assert state["fields"]["content_source"] == "file"
    assert state["fields"]["topic"] == ""
    assert "content_urls" not in state["fields"]


def test_url_normalisation_and_range_validation_before_post(ui_page):
    page, load = ui_page
    state = setup(page, load)
    fill(page)
    page.get_by_role("tab", name=re.compile("网页链接$")).click()
    page.get_by_role("textbox", name="内容链接").fill(
        "example.com/a,https://example.com/a\nhttps://example.com/b"
    )
    choose(page, "页数设置", "自定义范围")
    page.get_by_role("spinbutton", name="最少页数").fill("15")
    page.get_by_role("spinbutton", name="最多页数").fill("8")
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("最少页数不能大于最多页数")
    assert not state["writes"]
    page.get_by_role("spinbutton", name="最多页数").fill("20")
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    page.wait_for_function("outlineStreams.length===1")
    assert (
        state["fields"]["content_urls"].replace("\r\n", "\n")
        == "https://example.com/a\nhttps://example.com/b"
    )
    assert state["fields"]["min_pages"] == "15"
    assert state["fields"]["max_pages"] == "20"


def test_package_catalogue_failure_retry_and_svg_payload(ui_page):
    page, load = ui_page
    state = setup(page, load)
    fill(page)
    state["package_fail"] = True
    choose(page, "生成方式", "快速模式 · 模板包")
    expect(page.get_by_role("alert")).to_contain_text("模板包目录暂时不可用")
    expect(page.get_by_role("button", name="开始生成大纲", exact=True)).to_be_disabled()
    state["package_fail"] = False
    page.get_by_role("button", name="重试", exact=True).click()
    choose(page, "已发布模板包", "研发报告 · v2")
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    page.wait_for_function("outlineStreams.length===1")
    assert state["fields"]["package_version_id"] == "7"
    assert state["fields"]["render_mode"] == "svg"
    assert state["fields"]["generation_mode"] == "package"


def test_unattended_stop_confirmation_focus_failure_and_retry(ui_page):
    page, load = ui_page
    state = setup(page, load, active=True)
    stop = page.get_by_role("button", name="停止无人值守任务", exact=True)
    stop.click()
    modal = page.get_by_role("dialog", name="停止无人值守任务")
    expect(modal).to_be_visible()
    modal.get_by_role("button", name="取消", exact=True).focus()
    page.keyboard.press("Tab")
    assert modal.evaluate("e=>e.contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(stop).to_be_focused()
    assert not state["writes"]
    state["fail"] = True
    stop.click()
    modal.get_by_role("button", name="确认停止", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("暂时无法停止任务")
    expect(modal).to_be_visible()
    state["fail"] = False
    modal.get_by_role("button", name="确认停止", exact=True).click()
    expect(modal).not_to_be_visible()
    assert state["writes"] == [("/api/projects/ui-todo/unattended/cancel", "POST")] * 2
    assert page.evaluate("outlineStreams.length") == 0


def test_monitor_keeps_disclosure_and_focus_across_native_poll(ui_page):
    page, load = ui_page
    state = setup(page, load, active=True)
    summary = page.get_by_role("button", name=re.compile("阶段详情"))
    expect(summary).to_have_attribute("aria-expanded", "false")
    summary.click()
    expect(summary).to_have_attribute("aria-expanded", "true")
    summary.focus()
    state["run"]["overall_progress"] = 55
    page.wait_for_timeout(5100)
    expect(page.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "55")
    expect(summary).to_be_focused()
    expect(summary).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_text("另有 1 个阶段未选择，不会执行")).to_be_visible()
    assert all(method == "GET" for _, method in state["reads"])


def test_past_terminal_run_does_not_reload_or_restart_outline(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline")
    state["run"] = dict(
        task_status="completed",
        status="completed",
        topic="历史任务",
        overall_progress=100,
        stages=[],
    )
    # Native controller remains available to default hosts and exposes React data.
    page.evaluate(
        "run=>{window.testPast=0;window.pastMonitor=UnattendedMonitor.mount({container:document.createElement('div'),projectId:'ui-todo',initiallyActive:false,onRender:()=>{},onComplete:()=>testPast++});pastMonitor.destroy();pastMonitor.render(run);}",
        state["run"],
    )
    assert page.evaluate("testPast") == 0
    assert page.evaluate("outlineStreams.length") == 0


@pytest.mark.parametrize("width", [320, 390])
def test_long_mobile_title_keeps_theme_input_and_submit_reachable(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=568))
    setup(page, load, count_title=True)
    for control in [
        page.get_by_role("textbox", name="主题", exact=True),
        page.get_by_role("button", name="开始生成大纲", exact=True),
    ]:
        box = control.bounding_box()
        assert box["y"] + box["height"] <= 568
        assert control.evaluate(
            "e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}"
        )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
