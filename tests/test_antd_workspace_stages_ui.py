"""Shared workspace stage bar: server facts drive status, links never skip work."""

import re

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_home_generator_ui import setup_workspace, start
from test_antd_todo_ui import setup as setup_todo

STAGES = ["内容规划", "视觉设计", "页面生成", "编辑交付"]


def steps(page):
    return page.locator(".project-stages .ant-steps-item")


def statuses(page):
    items = steps(page)
    expect(items).to_have_count(4)
    result = []
    for index in range(4):
        classes = items.nth(index).get_attribute("class")
        status = re.search(r"ant-steps-item-(wait|process|finish|error)", classes).group(1)
        result.append((status, "ant-steps-item-disabled" in classes))
    return result


def step(page, name):
    return steps(page).filter(has_text=name)


def test_planning_page_without_outline_only_offers_planning(ui_page):
    page, load = ui_page
    state = setup_todo(page, load, scene="pending")
    for name in STAGES:
        expect(step(page, name)).to_have_count(1)
    assert statuses(page) == [("process", False), ("wait", True), ("wait", True), ("wait", True)]
    expect(page.locator(".project-stages").get_by_text("内容规划", exact=True)).to_have_attribute("aria-current", "step")
    step(page, "视觉设计").click(force=True)
    page.wait_for_timeout(200)
    assert page.url.endswith("/projects/ui-todo/todo")
    assert not state["writes"] and not state["errors"]


def test_confirmed_outline_links_to_existing_design_route(ui_page):
    page, load = ui_page
    setup_todo(page, load, scene="outline")
    assert statuses(page)[:2] == [("finish", False), ("process", False)]
    with page.expect_navigation():
        step(page, "视觉设计").click()
    assert page.url.endswith("/projects/ui-todo/template-selection")


@pytest.mark.parametrize("width", [1440, 390])
def test_generator_marks_generation_and_locks_design_while_running(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    state = setup_workspace(page, load, mode="global")
    assert statuses(page)[2] == ("process", False)
    start(page)
    assert statuses(page)[1] == ("finish", True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not [write for write in state["writes"] if "template" in write[0]]


def test_completed_generator_reaches_editor(ui_page):
    page, load = ui_page
    setup_workspace(page, load, mode="global", completed=True)
    assert statuses(page) == [("finish", False), ("finish", False), ("finish", False), ("process", False)]
    with page.expect_navigation():
        step(page, "编辑交付").click()
    assert page.url.endswith("/projects/ui-generator/edit")


def test_task_record_lists_generation_progress_in_a_drawer(ui_page):
    page, load = ui_page
    setup_workspace(page, load, mode="global")
    start(page)
    trigger = page.get_by_role("button", name="任务记录")
    trigger.click()
    drawer = page.get_by_role("dialog", name="任务记录")
    expect(drawer).to_be_visible()
    expect(drawer.locator(".ant-timeline-item")).not_to_have_count(0)
    page.keyboard.press("Escape")
    expect(drawer).not_to_be_visible()


def test_generation_stage_can_return_to_the_explicit_planning_view(ui_page):
    page, load = ui_page
    setup_workspace(page, load, mode="global", completed=True)
    with page.expect_navigation():
        step(page, "内容规划").click()
    assert page.url.endswith("/projects/ui-generator/todo?view=planning")
