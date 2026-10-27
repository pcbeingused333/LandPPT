"""Generation state reaches Ant controls without an inert DOM or replaying work."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_home_generator_ui import ORIGINAL, send, setup_workspace, slide, start


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_cached_restore_reads_saved_results_without_new_stream_or_writes(
    ui_page, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1))
    held = []
    page.route("**/api/projects/ui-generator", lambda route: held.append(route))
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))"
    )
    assert page.evaluate("testStreams[0].readyState") == 2
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))"
    )
    expect(page.locator("#generatorStatusUI [role=status]")).to_contain_text(
        "正在读取后台生成结果"
    )
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL
    assert page.get_by_role("button", name="开始生成", exact=True).count() == 0
    assert len(held) == 1
    held[0].fulfill(json=dict(status="completed", slides_data=[slide(1), slide(2)]))
    expect(
        page.get_by_role("heading", name="页面预览", exact=True)
    ).to_be_visible()
    assert page.evaluate("testStreams.length") == 1
    assert (
        page.locator("#generatorControlState, #generationStatus, #startBtn").count()
        == 0
    )
    assert not state["writes"] and not errors
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_resume_failure_stays_paused_and_explains_why_without_starting_work(
    ui_page, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    setup_workspace(page, load)
    start(page)
    page.get_by_role("button", name="暂停", exact=True).click()
    page.route(
        "**/slides/clear-cancel",
        lambda route: route.fulfill(
            json=dict(success=False, error="任务服务暂时不可用")
        ),
    )
    page.get_by_role("button", name="继续", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("恢复失败：任务服务暂时不可用")
    expect(page.get_by_role("heading", name="生成已暂停", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="继续", exact=True)).to_be_enabled()
    assert page.evaluate("testStreams.length") == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_stop_failure_does_not_silently_claim_server_cancellation(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    page.route(
        "**/slides/cancel",
        lambda route: route.fulfill(status=503, json=dict(error="稍后重试")),
    )
    page.get_by_role("button", name="停止生成", exact=True).click()
    page.get_by_role("dialog", name="操作确认").get_by_role(
        "button", name="确认", exact=True
    ).click()
    expect(
        page.get_by_role("alert").filter(has_text="停止请求尚未确认")
    ).to_contain_text("后台任务可能仍在运行")
    expect(page.get_by_role("button", name="继续生成", exact=True)).to_be_enabled()
    assert page.evaluate("testStreams[0].readyState") == 2


def test_leaving_during_pending_resume_cannot_open_a_late_stream(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    page.get_by_role("button", name="暂停", exact=True).click()
    held = []
    page.route("**/slides/clear-cancel", lambda route: held.append(route))
    page.get_by_role("button", name="继续", exact=True).click()
    page.wait_for_timeout(50)
    assert len(held) == 1
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))"
    )
    held[0].fulfill(json=dict(success=True))
    page.wait_for_timeout(80)
    assert page.evaluate("testStreams.length") == 1


def test_stale_stream_events_cannot_overwrite_a_paused_run(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1))
    page.get_by_role("button", name="暂停", exact=True).click()
    send(page, type="complete", message="过期的完成事件")
    expect(page.get_by_role("heading", name="生成已暂停", exact=True)).to_be_visible()
    expect(page.locator("#generatorStatusUI")).not_to_contain_text("过期的完成事件")
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL


def test_new_page_replaces_failed_preview_and_preserves_edited_replay(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(
        page,
        type="slide",
        slide_data={
            **slide(1),
            "generation_failed": True,
            "html_content": "<body>Failed</body>",
        },
    )
    expect(
        page.locator("#slide-1 [title='设计生成未完成，请重新生成此页']")
    ).to_have_count(1)
    send(page, type="slide", slide_data={**slide(1), "is_user_edited": True})
    expect(
        page.locator("#slide-1 [title='设计生成未完成，请重新生成此页']")
    ).to_have_count(0)
    send(
        page,
        type="slide_skipped",
        slide_data={**slide(1), "html_content": "<body>Stale</body>"},
    )
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL
    page.locator("#slide-1 button[title='全屏查看']").click()
    assert page.get_by_title("幻灯片全屏预览", exact=True).get_attribute("srcdoc") == ORIGINAL
    page.keyboard.press("Escape")
    expect(page.locator(".generator-document-modal")).not_to_be_visible()


def test_permission_loss_ends_cached_recovery_and_disables_restart(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    page.route(
        "**/api/projects/ui-generator",
        lambda route: route.fulfill(status=403, json=dict(detail="Forbidden")),
    )
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));"
    )
    expect(page.get_by_role("alert")).to_contain_text("项目不可访问")
    assert (
        page.locator("#ui-startBtn, #ui-resumeBtn, #ui-pauseBtn, #ui-stopBtn").count()
        == 0
    )
    assert page.evaluate("testStreams.length") == 1


def test_generated_titles_and_status_messages_are_text(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    text = '</script><img src=x onerror="window.statusInjection=true">'
    send(page, type="slide", slide_data={**slide(1), "title": text})
    send(page, type="error", message=text)
    expect(page.get_by_role("alert")).to_have_text(text)
    expect(page.locator("#slide-1 .slide-title")).to_have_text(text)
    assert (
        page.locator("#generatorStatusUI img, #slide-1 .slide-header img").count() == 0
    )
    assert not page.evaluate("window.statusInjection || false")


def test_task_record_reports_actual_page_numbers_for_out_of_order_completion(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(2), total=3)
    page.get_by_role("button", name="任务记录", exact=True).click()
    drawer = page.get_by_role("dialog", name="任务记录", exact=True)
    expect(drawer).to_contain_text("第 2 / 3 页已完成")
    expect(drawer).not_to_contain_text("第 1 / 3 页已完成")
