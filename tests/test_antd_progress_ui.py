"""Fractional API progress must render as bounded integer percentages."""

from datetime import datetime

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, detail_project, generator_page, ui_page  # noqa: F401
from test_antd_ui import settings


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("value,expected", [(-3, 0), (0, 0), (33.333333333333336, 33), (66.66666666666667, 67), (99.7, 100), (140, 100)])
@pytest.mark.parametrize("scene", ["dashboard", "list", "detail"])
def test_project_progress_labels_and_accessibility_are_integers(
    ui_page, detail_project, width, value, expected, scene
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=844))
    board = dict(task_id="ui-detail", title="你好，世界", overall_progress=value,
                 current_stage_index=0, stages=[dict(id="ppt", name="PPT生成", description="正在生成页面", status="running", progress=value)])
    project = {**detail_project, "status": "in_progress", "topic": "展示精度", "updated_at": datetime(2026, 7, 28).timestamp(), "todo_board": board}
    if scene == "dashboard":
        load("pages/project/project_dashboard.html", path="/dashboard", recent_projects=[project], active_todo_boards=[board])
        containers = [page.locator(".dashboard-recent"), page.locator(".dashboard-tasks")]
    elif scene == "list":
        load("pages/project/projects_list.html", projects=[project])
        containers = [page.locator(".project-collection .mobile-projects")]
    else:
        load("pages/project/project_detail.html", path="/projects/ui-detail", project=project, todo_board=board, versions=[])
        containers = [page.locator(".detail-progress-card")]
        expect(page.locator(".detail-progress-summary")).to_contain_text(f"{expected}%")
    for container in containers:
        bars = container.get_by_role("progressbar")
        expect(bars.first).to_be_visible()
        assert bars.count() == (2 if scene == "detail" else 1)
        for bar in bars.all():
            expect(bar).to_have_attribute("aria-valuenow", str(expected))
        if expected < 100:
            expect(container).to_contain_text(f"{expected}%")
        assert f"{value}%" not in container.inner_text() or value == expected
    # Rendering must not round the backend's serialized calculation.
    payload = page.locator("#antdData").text_content()
    assert str(value) in payload
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_unattended_total_progress_uses_the_same_integer_display(generator_page):
    page, open_workspace, _, _, _, _, errors = generator_page
    page.route("**/unattended/status", lambda route: route.fulfill(json={"run": dict(
        task_status="running", status="running", topic="生成中", overall_progress=66.66666666666667,
        stages=[dict(id="ppt", name="生成幻灯片", status="running")])}))
    open_workspace("running")
    progress = page.get_by_role("progressbar", name="任务总进度")
    expect(progress).to_have_attribute("aria-valuenow", "67")
    expect(page.locator(".unattended-ant")).to_contain_text("67%")
    assert not errors


@pytest.mark.parametrize("admin", [True, False])
def test_landppt_model_controls_remain_without_the_credentials_notice(ui_page, admin):
    page, load = ui_page
    settings(page, load, current_provider="landppt", current_config={"landppt_model": "MODEL1"}, user=dict(username="test", is_admin=admin))
    expect(page.locator("#field-landppt_model")).to_be_visible()
    assert page.get_by_text("LandPPT 服务凭据由管理员统一维护，此处仅设置当前账号的模型。", exact=True).count() == 0
    expect(page.get_by_role("button", name="保存 LandPPT", exact=True)).to_be_visible()
