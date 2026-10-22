"""Real generation controller with bounded React skeleton previews and SSE events."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_home_generator_ui import ORIGINAL, send, setup_workspace, slide, start

SIZES = [(1910, 915), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


@pytest.fixture(autouse=True)
def bootstrap_modal_reset(ui_page):
    # The CDN scripts are blocked in the isolated fixture. Retain Bootstrap's
    # hidden modal baseline, as the live workspace and generator_page do.
    page, _ = ui_page
    page.route("**/bootstrap@5.1.3/dist/css/bootstrap.min.css", lambda route: route.fulfill(
        body="*,::before,::after{box-sizing:border-box}.d-flex{display:flex!important}"
        ".align-items-center{align-items:center!important}.modal{display:none;position:fixed;inset:0}",
        content_type="text/css",
    ))


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("mode", ["package", "global"])
def test_first_preview_keeps_its_width_as_more_pages_arrive(ui_page, width, height, mode):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = setup_workspace(page, load, mode=mode)
    start(page)
    send(page, type="progress", total=6, completed=0, message="设计页面")
    expect(page.locator(".generator-skeleton-card")).to_have_count(6)
    expect(page.locator(".generator-skeleton-card .ant-skeleton-active").first).to_be_visible()
    send(page, type="slide", slide_data=slide(1))
    expect(page.locator(".generator-skeleton-card")).to_have_count(5)
    card = page.locator("#slide-1")
    first_width = card.bounding_box()["width"]
    assert first_width <= 440.5
    expect(page.locator(".generator-preview-count")).to_have_attribute("aria-label", "已生成 1 / 6 页")
    send(page, type="slide", slide_data=slide(2))
    expect(page.locator(".generator-skeleton-card")).to_have_count(4)
    assert abs(card.bounding_box()["width"] - first_width) < 1.5
    send(page, type="complete", total=2, succeeded=2, message="全部完成")
    expect(page.locator(".generator-skeleton-card")).to_have_count(0)
    expect(page.get_by_role("heading", name="演示文稿已生成")).to_be_visible()
    assert abs(card.bounding_box()["width"] - first_width) < 1.5
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for frame in page.locator(".slide-preview iframe").all():
        assert frame.get_attribute("srcdoc") == ORIGINAL
        preview = frame.locator("..").bounding_box()
        box = frame.bounding_box()
        assert abs(box["width"] - preview["width"]) < 1.5
        assert abs(box["height"] - preview["height"]) < 1.5
    card.locator(".fullscreen-btn").click()
    assert page.get_by_title("幻灯片全屏预览", exact=True).get_attribute("srcdoc") == ORIGINAL
    page.keyboard.press("Escape")
    expect(page.locator(".generator-document-modal")).not_to_be_visible()
    assert not state["writes"] and not errors


def test_out_of_order_pages_replace_their_own_skeleton_and_keep_visual_order(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="progress", total=4, current=2)
    expect(page.locator(".generator-skeleton-card.is-current")).to_have_count(1)
    send(page, type="slide", slide_data=slide(2))
    expect(page.locator(".generator-skeleton-card")).to_have_count(3)
    pending = page.locator(".generator-skeleton-card").first.bounding_box()
    ready = page.locator("#slide-2").bounding_box()
    assert pending["y"] < ready["y"] or (pending["y"] == ready["y"] and pending["x"] < ready["x"])
    send(page, type="slide", slide_data=slide(1))
    send(page, type="slide", slide_data=slide(1))
    expect(page.locator("#slidesContainer > .slide-card")).to_have_count(2)
    expect(page.locator(".generator-skeleton-card")).to_have_count(2)
    expect(page.locator(".generator-skeleton-title").first).to_have_text("待生成页面")
    assert page.locator("#slide-1").bounding_box()["x"] < page.locator("#slide-2").bounding_box()["x"]


def test_pause_reconnect_resume_and_restart_restore_only_pending_placeholders(ui_page):
    page, load = ui_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1))
    expect(page.locator(".generator-skeleton-card")).to_have_count(1)
    page.get_by_role("button", name="暂停", exact=True).click()
    expect(page.get_by_role("heading", name="生成已暂停")).to_be_visible()
    assert page.locator(".generator-skeleton-card .ant-skeleton-active").count() == 0
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL
    page.get_by_role("button", name="继续", exact=True).click()
    # Resume clears the backend cancellation flag before creating a new stream.
    # The existing skeleton starts animating before that request completes.
    page.wait_for_function("testStreams.length === 2 && testStreams.at(-1).readyState === 1")
    expect(page.locator("#generatorStatusUI .ant-badge-status-text")).to_have_text("正在生成")
    expect(page.locator(".generator-skeleton-card .ant-skeleton-active").first).to_be_visible()
    page.evaluate("testStreams.at(-1).readyState = 0; testStreams.at(-1).onerror({})")
    expect(page.get_by_role("heading", name="正在恢复连接")).to_be_visible()
    assert page.locator(".generator-skeleton-card .ant-skeleton-active").count() == 0
    # A closed source cannot reopen. The controller owns a new source and
    # rejects callbacks from the stale one while reconnecting.
    page.wait_for_function("testStreams.length === 3 && testStreams.at(-1).readyState === 1")
    expect(page.get_by_role("heading", name="演示文稿正在成形")).to_be_visible()
    send(page, type="error", message="服务暂时不可用")
    expect(page.locator(".generator-skeleton-card")).to_have_count(0)
    page.get_by_role("button", name="重新开始", exact=True).click()
    # Restart rehydrates stored pages from the same stream's skipped events;
    # the waiting UI follows that controller contract rather than caching slides.
    expect(page.locator(".generator-skeleton-card")).to_have_count(2)
    send(page, type="slide_skipped", slide_data=slide(1), total=2)
    expect(page.locator(".generator-skeleton-card")).to_have_count(1)
    expect(page.locator(".generator-skeleton-card .ant-skeleton-active").first).to_be_visible()
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL
    assert len(state["writes"]) == 2 and not errors


@pytest.mark.parametrize("terminal", ["error", "partial", "stop"])
def test_terminal_state_removes_waiting_animation_and_preserves_generated_page(ui_page, terminal):
    page, load = ui_page
    state = setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1))
    if terminal == "stop":
        page.get_by_role("button", name="停止生成", exact=True).click()
        page.get_by_role("dialog", name="操作确认").get_by_role("button", name="确认", exact=True).click()
    elif terminal == "partial":
        send(page, type="complete", total=2, succeeded=1, partial=True, message="部分页面待重新生成")
    else:
        send(page, type="error", message="生成失败，已保存内容")
    expect(page.locator(".generator-skeleton-card")).to_have_count(0)
    expect(page.locator("#slide-1")).to_be_visible()
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL
    assert page.evaluate("testStreams.at(-1).readyState") == 2
    assert len(state["writes"]) == (1 if terminal == "stop" else 0)


def test_idle_outline_is_static_and_reduced_motion_disables_running_shimmer(ui_page):
    page, load = ui_page
    page.emulate_media(reduced_motion="reduce")
    setup_workspace(page, load)
    expect(page.locator(".generator-skeleton-title").first).to_have_text("封面")
    assert page.locator(".generator-skeleton-card .ant-skeleton-active").count() == 0
    assert page.evaluate("testStreams.length") == 0
    start(page)
    expect(page.locator(".generator-skeleton-card .ant-skeleton-active").first).to_be_visible()
    assert page.locator(".generator-skeleton-canvas h3").first.evaluate("e => getComputedStyle(e).animationName") == "none"
    assert page.locator(".generator-preview-eyebrow .anticon").evaluate("e => getComputedStyle(e).animationName") == "none"


def test_large_total_bounds_placeholder_dom_and_complete_single_page_width(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="progress", total=500, completed=0, message="准备页面")
    expect(page.locator(".generator-skeleton-card")).to_have_count(6)
    expect(page.locator(".generator-preview-count")).to_have_attribute("aria-label", "已生成 0 / 500 页")
    send(page, type="slide", slide_data=slide(1))
    send(page, type="complete", total=1, succeeded=1, message="完成")
    expect(page.locator(".generator-skeleton-card")).to_have_count(0)
    assert page.locator("#slide-1").bounding_box()["width"] <= 440.5


def test_unknown_total_does_not_invent_page_count_or_progress(ui_page):
    page, load = ui_page
    setup_workspace(page, load, outline_titles=[])
    expect(page.get_by_role("heading", name="准备生成演示文稿")).to_be_visible()
    start(page)
    expect(page.locator(".generator-skeleton-card")).to_have_count(3)
    expect(page.locator(".generator-preview-count")).to_have_attribute("aria-label", "已生成 0 页")
    expect(page.locator("#generatorStatusUI [role=progressbar]")).to_have_attribute("aria-valuenow", "0")
    send(page, type="slide", slide_data=slide(1))
    expect(page.locator(".generator-preview-count")).to_have_attribute("aria-label", "已生成 1 页")
    expect(page.locator(".generator-skeleton-card")).to_have_count(3)


def test_completion_uses_available_page_count_reported_by_server(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1))
    send(page, type="complete", total=3, succeeded=3, message="页面已保存")
    expect(page.locator(".generator-preview-count")).to_have_attribute("aria-label", "已生成 3 / 3 页")
    expect(page.locator(".generator-skeleton-card")).to_have_count(0)


def test_outline_titles_are_text_and_generated_frames_are_not_restyled(ui_page):
    page, load = ui_page
    title = '</script><script>window.injection=true</script>'
    setup_workspace(page, load, outline_titles=[title, "长标题" * 100])
    expect(page.locator(".generator-skeleton-title").first).to_have_text(title)
    assert page.evaluate("window.injection") is None
    assert page.evaluate("document.documentElement.scrollWidth") <= 1440
    start(page)
    send(page, type="slide", slide_data=slide(1))
    assert page.locator("#slide-1 iframe").get_attribute("srcdoc") == ORIGINAL


@pytest.mark.parametrize("task_status", ["failed", "cancelled"])
def test_unattended_terminal_run_stops_empty_waiting_animation(ui_page, task_status):
    page, load = ui_page
    run = {
        "task_status": task_status, "status": task_status, "topic": "示例任务", "stages": [],
        "error": "设计服务不可用" if task_status == "failed" else None,
    }
    setup_workspace(page, load, active=True, unattended_run=run)
    expect(page.get_by_role("heading", name="生成暂未完成")).to_be_visible()
    expect(page.locator(".generator-skeleton-card")).to_have_count(0)
    assert page.locator(".generator-ant-actions button").count() == 0
