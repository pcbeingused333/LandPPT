"""Project-scoped Agent controls keep previews explicit and recover live runs."""

from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, detail_project, ui_page  # noqa: F401

OUT = Path("artifacts/project-agent-20261023")


def setup(page, load, project, task=None):
    state = {
        "task": task,
        "writes": [],
        "errors": [],
        "context": {"revision": "a" * 64, "pages": [{"index": 0, "title": "封面"}]},
    }
    page.on("pageerror", lambda error: state["errors"].append(str(error)))

    def api(route):
        call = route.request
        if call.method == "GET":
            route.fulfill(
                json={
                    "success": True,
                    "task": state["task"],
                    "context": state["context"],
                }
            )
            return
        state["writes"].append((call.url, call.post_data_json))
        if call.url.endswith("/apply"):
            state["task"]["result"]["applied"] = True
        elif call.url.endswith("/cancel"):
            state["task"]["status"] = "cancelled"
        else:
            state["task"] = {
                "task_id": "run-new",
                "status": "running",
                "instruction": call.post_data_json["instruction"],
                "result": {"steps": ["读取项目上下文"]},
            }
        route.fulfill(json={"success": True, "task_id": "run-new"})

    page.route("**/api/projects/ui-test/agent**", api)
    load(
        "pages/project/project_detail.html",
        path="/projects/ui-test",
        project={**project, "project_id": "ui-test"},
        todo_board=None,
        versions=[],
    )
    page.get_by_role("button", name="项目助手", exact=True).click()
    drawer = page.get_by_role("dialog", name="项目助手", exact=True)
    expect(drawer).to_be_visible()
    expect(drawer.get_by_role("button", name="刷新任务")).to_be_enabled()
    return state, drawer


@pytest.mark.parametrize("size", [(1440, 900), (390, 844), (320, 568), (844, 390)])
def test_agent_layout_keeps_native_controls_and_no_automatic_writes(
    ui_page, detail_project, size
):
    page, load = ui_page
    page.set_viewport_size(dict(zip(["width", "height"], size)))
    state, drawer = setup(page, load, detail_project)
    drawer.get_by_role("textbox", name="项目助手要求").fill("检查整个项目的结构")
    assert drawer.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"agent-{size[0]}x{size[1]}.png"))
    page.keyboard.press("Escape")
    expect(drawer).not_to_be_visible()
    expect(page.get_by_role("button", name="项目助手", exact=True)).to_be_focused()
    page.get_by_role("button", name="项目助手", exact=True).click()
    expect(drawer.get_by_role("textbox", name="项目助手要求")).to_have_value(
        "检查整个项目的结构"
    )
    assert not state["writes"] and not state["errors"]


def test_send_exact_scope_no_double_submission_and_cancel(ui_page, detail_project):
    page, load = ui_page
    state, drawer = setup(page, load, detail_project)
    drawer.get_by_role("textbox", name="项目助手要求").fill("解释项目")
    drawer.get_by_role("button", name="发送请求", exact=True).click()
    expect(drawer.get_by_role("button", name="停止任务")).to_be_visible()
    assert len(state["writes"]) == 1
    assert state["writes"][0][1] == {
        "instruction": "解释项目",
        "indices": [],
        "project_revision": "a" * 64,
    }
    expect(drawer.get_by_role("textbox", name="项目助手要求")).to_be_disabled()
    drawer.get_by_role("button", name="停止任务").click()
    expect(drawer.get_by_text("已停止", exact=True)).to_be_visible()
    assert len(state["writes"]) == 2 and state["writes"][1][0].endswith("/cancel")


def test_completed_preview_requires_confirmation_and_renders_diff_as_text(
    ui_page, detail_project
):
    page, load = ui_page
    state, drawer = setup(
        page,
        load,
        detail_project,
        {
            "task_id": "run-preview",
            "status": "completed",
            "instruction": "精简文案",
            "result": {
                "summary": "预览完成",
                "steps": ["已检查页面"],
                "pages": [
                    {
                        "slide_index": 0,
                        "title": "封面",
                        "summary": "表达简洁",
                        "diff": "<img src=x onerror=alert(1)>",
                    }
                ],
            },
        },
    )
    drawer.get_by_text("第 1 页 · 封面", exact=True).click()
    expect(drawer.locator("pre")).to_contain_text("<img")
    assert drawer.locator("pre img").count() == 0
    drawer.get_by_role("button", name="应用 1 页修改").click()
    confirm = page.get_by_role("dialog", name="应用这 1 页修改？", exact=True)
    confirm.get_by_role("button", name="继续检查").click()
    assert not state["writes"]
    drawer.get_by_role("button", name="应用 1 页修改").click()
    page.get_by_role("dialog", name="应用这 1 页修改？").get_by_role(
        "button", name="确认应用"
    ).click()
    expect(drawer.get_by_text("这批修改已保存", exact=True)).to_be_visible()
    assert len(state["writes"]) == 1 and state["writes"][0][0].endswith("/apply")


def test_active_job_restores_after_close_and_keyboard_cannot_submit(
    ui_page, detail_project
):
    page, load = ui_page
    state, drawer = setup(
        page,
        load,
        detail_project,
        {
            "task_id": "run-live",
            "status": "running",
            "instruction": "精简",
            "result": {"steps": ["读取项目上下文"]},
        },
    )
    expect(drawer.get_by_role("button", name="停止任务")).to_be_visible()
    page.keyboard.press("Control+s")
    page.keyboard.press("Escape")
    expect(drawer).not_to_be_visible()
    page.get_by_role("button", name="项目助手", exact=True).click()
    expect(drawer.get_by_role("button", name="停止任务")).to_be_visible()
    assert not state["writes"] and not state["errors"]


def test_selected_scope_is_sent_and_conflict_keeps_preview(ui_page, detail_project):
    page, load = ui_page
    state, drawer = setup(page, load, detail_project)
    drawer.get_by_role("combobox", name="项目助手页面范围").click()
    page.locator(".ant-select-item-option").first.click()
    page.keyboard.press("Escape")
    expect(drawer).to_be_visible()
    drawer.get_by_role("textbox", name="项目助手要求").fill("精简第1页")
    drawer.get_by_role("button", name="发送请求", exact=True).click()
    expect(drawer.get_by_role("button", name="停止任务")).to_be_visible()
    assert state["writes"][0][1]["indices"] == [0]
    state["task"] = {
        "task_id": "run-new",
        "status": "completed",
        "result": {"pages": [{"slide_index": 0, "title": "封面", "diff": "保留草稿"}]},
    }
    drawer.get_by_role("button", name="刷新任务").click()
    expect(drawer.get_by_role("button", name="应用 1 页修改")).to_be_enabled()
    page.route(
        "**/agent/run-new/apply",
        lambda route: route.fulfill(
            status=409, json={"detail": "项目已更新，本批未保存"}
        ),
    )
    drawer.get_by_role("button", name="应用 1 页修改").click()
    confirm = page.get_by_role("dialog", name="应用这 1 页修改？")
    confirm.get_by_role("button", name="确认应用").click()
    expect(drawer.get_by_text("项目已更新，本批未保存")).to_be_visible()
    confirm.get_by_role("button", name="继续检查").click()
    expect(drawer.get_by_role("button", name="应用 1 页修改")).to_be_visible()
