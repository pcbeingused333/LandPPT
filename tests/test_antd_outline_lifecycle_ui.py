"""Built planning workspace lifecycle, recovery and stream-view boundaries."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_todo_ui import OUTLINE, fill, setup


def begin(page, load):
    state = setup(page, load)
    fill(page)
    page.get_by_role("button", name="开始生成大纲", exact=True).click()
    page.wait_for_function("outlineStreams.length === 1")
    return state


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_disconnect_uses_real_recovery_banner_and_one_generation(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    state = begin(page, load)
    held = []
    page.route("**/api/projects/ui-todo", lambda route: held.append(route))
    page.evaluate("outlineStreams[0].close()")
    recovery = page.get_by_role("alert").filter(has_text="连接暂时中断")
    expect(recovery).to_be_visible()
    expect(page.get_by_role("button", name="重新生成", exact=True)).to_be_disabled()
    assert len(held) == 1
    held[0].fulfill(json={"outline": OUTLINE})
    expect(recovery).not_to_be_visible()
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    expect(page.get_by_role("button", name="开始生成 PPT", exact=True)).to_be_enabled()
    assert page.evaluate("outlineStreams.length") == 1
    assert state["writes"] == [("/projects/ui-todo/confirm-requirements", "POST")]
    assert not state["errors"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_pagehide_aborts_stream_and_bfcache_restore_keeps_partial_text_without_restarting(
    ui_page,
):
    page, load = ui_page
    state = begin(page, load)
    page.evaluate("sendOutline({content:'已经收到的部分内容，需要在返回页面后保留。'})")
    preview = page.get_by_label("大纲实时输出", exact=True)
    expect(preview).to_contain_text("已经收到的部分内容")
    held = []
    page.route("**/api/projects/ui-todo", lambda route: held.append(route))
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}))"
    )
    page.wait_for_function("outlineRequests[0].signal.aborted && outlineCancels >= 1")
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))"
    )
    expect(page.get_by_role("alert")).to_contain_text("连接暂时中断")
    expect(preview).to_contain_text("已经收到的部分内容")
    assert len(held) == 1
    held[0].fulfill(json={"outline": OUTLINE})
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    assert page.evaluate("outlineStreams.length") == 1
    assert len(state["writes"]) == 1 and not state["errors"]


def test_pretext_load_failure_uses_safe_plain_text_and_does_not_stop_stream(ui_page):
    page, load = ui_page
    page.route("**/outlineStreamPretextRenderer.js?*", lambda route: route.abort())
    state = begin(page, load)
    text = '</div><img src=x onerror="window.outlineInjection=true"><script>window.outlineInjection=true</script>'
    page.evaluate("text => sendOutline({content:text})", text)
    preview = page.get_by_label("大纲实时输出", exact=True)
    expect(preview).to_contain_text(text)
    assert not preview.locator("img, script").count()
    assert not page.evaluate("window.outlineInjection || false")
    page.evaluate("outline => sendOutline({outline,done:true})", OUTLINE)
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    assert not state["errors"]


def test_failed_saved_stage_offers_retry_without_an_automatic_stream(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="failed", stage_status="failed")
    expect(page.locator(".todo-outline-ant").get_by_role("alert")).to_contain_text(
        "上次大纲生成失败"
    )
    assert page.evaluate("outlineStreams.length") == 0
    expect(page.get_by_role("button", name="重新生成", exact=True)).to_be_enabled()
    assert not page.get_by_role("button", name="开始生成 PPT", exact=True).count()
    page.get_by_role("button", name="重新生成", exact=True).click()
    page.get_by_role("dialog", name="重新生成大纲", exact=True).get_by_role(
        "button", name="重新生成", exact=True
    ).click()
    page.wait_for_function("outlineStreams.length === 1")
    page.evaluate("outline => sendOutline({outline,done:true})", OUTLINE)
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    assert not state["errors"]


def test_existing_outline_wins_over_stale_running_stage_without_generation(ui_page):
    page, load = ui_page
    state = setup(page, load, scene="outline", stage_status="running")
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    assert page.evaluate("outlineStreams.length") == 0
    assert page.locator("#todoLegacyHost, #outline-content-display").count() == 0
    assert page.evaluate("typeof window.LandPPTTodoUI === 'undefined'")
    assert not state["writes"] and not state["errors"]


def test_second_run_uses_current_text_and_keeps_scroll_and_jump_action(ui_page):
    page, load = ui_page
    state = begin(page, load)
    page.evaluate("outline => sendOutline({outline,done:true})", OUTLINE)
    expect(page.locator(".todo-outline-grid")).to_be_visible()
    page.get_by_role("button", name="重新生成", exact=True).click()
    page.get_by_role("dialog", name="重新生成大纲", exact=True).get_by_role(
        "button", name="重新生成", exact=True
    ).click()
    page.wait_for_function("outlineStreams.length === 2")
    page.evaluate(
        "sendOutline({content:Array.from({length:100},(_,i)=>'新一轮章节 '+i+'：保留阅读位置。').join('\\n')})"
    )
    preview = page.get_by_label("大纲实时输出", exact=True)
    expect(preview).to_contain_text("新一轮章节 99")
    preview.hover()
    page.mouse.wheel(0, -140)
    jump = page.get_by_role("button", name="回到最新", exact=True)
    expect(jump).to_be_visible()
    top = preview.evaluate("e => e.scrollTop")
    page.evaluate("sendOutline({content:'\\n仅属于第二轮的输出'})")
    expect(preview).to_contain_text("仅属于第二轮的输出")
    assert abs(preview.evaluate("e => e.scrollTop") - top) < 2
    jump.click()
    expect(jump).not_to_be_visible()
    assert preview.evaluate("e => e.scrollHeight-e.scrollTop-e.clientHeight") <= 28
    assert not state["errors"]


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_completed_project_explains_outline_edits_and_keeps_editor_access(
    ui_page, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    state = setup(page, load, scene="outline", has_output=True)
    expect(page.get_by_role("button", name="编辑 JSON", exact=True)).to_be_enabled()
    expect(
        page.get_by_role("alert").filter(has_text="不会自动更新已生成页面")
    ).to_be_visible()
    assert not page.get_by_role("button", name="开始生成 PPT", exact=True).count()
    with page.expect_navigation():
        page.locator(".project-stages .ant-steps-item").filter(
            has_text="编辑交付"
        ).click()
    assert page.url.endswith("/projects/ui-todo/edit")
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_background_page_generation_makes_planning_read_only(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    state = setup(
        page,
        load,
        scene="outline",
        has_output=True,
        start_stage=True,
        ppt_stage_status="running",
    )
    expect(page.get_by_role("alert").filter(has_text="生成任务进行中")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 JSON", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="重新生成", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="查看第 1 页", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="导出大纲 JSON", exact=True)).to_be_enabled()
    assert page.evaluate("outlineStreams.length") == 0
    assert not state["writes"] and not state["errors"]
