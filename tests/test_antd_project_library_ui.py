"""Favorites/pins retain server query state and use bounded native Ant controls."""

from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, detail_project, ui_page  # noqa: F401


@pytest.mark.parametrize("template", ["projects_list", "project_dashboard"])
@pytest.mark.parametrize("width", [1440, 390, 320])
def test_library_menu_failure_retry_and_authoritative_reload(
    ui_page, detail_project, template, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    errors, writes, pending = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    project = dict(
        detail_project,
        updated_at=detail_project["created_at"],
        is_favorite=True,
        is_pinned=True,
    )
    path = "/dashboard" if template == "project_dashboard" else "/projects"
    load(
        f"pages/project/{template}.html",
        path=path,
        projects=[project],
        recent_projects=[project],
    )
    title = page.locator(".project-library-title:visible")
    if template == "project_dashboard":
        page.get_by_role("textbox", name="PPT 主题", exact=True).fill(
            "尚未提交的创建主题"
        )
    expect(title.get_by_label("已置顶", exact=True)).to_be_visible()
    expect(title.get_by_label("已收藏", exact=True)).to_be_visible()
    # Reload receives authoritative server flags, not a reordered local page.
    html = page.evaluate(
        """() => {
        const clone = document.documentElement.cloneNode(true);
        clone.querySelector('#antdRoot').replaceChildren();
        const script = clone.querySelector('#antdData');
        const data = JSON.parse(script.textContent);
        data.projects[0].is_pinned = false;
        script.textContent = JSON.stringify(data);
        return '<!doctype html>' + clone.outerHTML;
    }"""
    )
    page.route(
        "**" + path, lambda route: route.fulfill(body=html, content_type="text/html")
    )

    def write(route):
        writes.append(route.request.post_data_json)
        if len(writes) == 1:
            route.fulfill(status=500, json={"detail": "整理失败，请重试"})
        else:
            pending.append(route)

    page.route("**/api/projects/*/library-preferences", write)
    trigger = title.get_by_role("button", name="整理项目", exact=True)
    trigger.click()
    page.get_by_role("menuitem", name="取消置顶", exact=True).click()
    expect(page.get_by_text("整理失败，请重试", exact=True)).to_be_visible()
    expect(title.get_by_label("已置顶", exact=True)).to_be_visible()
    expect(trigger).to_be_enabled()
    trigger.click()
    page.get_by_role("menuitem", name="取消置顶", exact=True).click()
    expect(trigger).to_be_disabled()
    assert len(pending) == 1 and writes == [{"is_pinned": False}] * 2
    if template == "project_dashboard":
        pending[0].fulfill(
            json={"status": "success", "is_favorite": True, "is_pinned": False}
        )
        expect(page.get_by_role("textbox", name="PPT 主题", exact=True)).to_have_value(
            "尚未提交的创建主题"
        )
    else:
        with page.expect_navigation(wait_until="domcontentloaded"):
            pending[0].fulfill(
                json={"status": "success", "is_favorite": True, "is_pinned": False}
            )
    expect(title.get_by_label("已置顶", exact=True)).to_have_count(0)
    expect(title.get_by_label("已收藏", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors
    button_box = trigger.bounding_box()
    assert button_box["height"] >= (44 if width < 600 else 32)


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_favorite_tabs_search_status_sort_and_pagination_keep_committed_filters(
    ui_page, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    query = "/projects?favorite=true&status=draft&search=Data&sort=updated&page=2"
    load(
        "pages/project/projects_list.html",
        path=query,
        favorite_filter=True,
        sort_order="updated",
        status_filter="draft",
        search_query="Data",
        page=2,
        total=35,
        page_size=10,
    )
    expect(page.get_by_role("tab", name="我的收藏", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.locator(".ant-pagination-next button").click()
    page.wait_for_url(lambda url: parse_qs(urlsplit(url).query).get("page") == ["3"])
    params = parse_qs(urlsplit(page.url).query)
    assert params["favorite"] == ["true"] and params["sort"] == ["updated"]
    assert params["search"] == ["Data"] and params["status"] == ["draft"]
    page.get_by_role("tab", name="全部项目", exact=True).click()
    page.wait_for_url(lambda url: "favorite" not in parse_qs(urlsplit(url).query))
    params = parse_qs(urlsplit(page.url).query)
    assert "page" not in params and params["search"] == ["Data"]
    assert params["sort"] == ["updated"] and params["status"] == ["draft"]
    page.locator("#projectSort").click()
    page.locator(".ant-select-dropdown:visible").get_by_text(
        "置顶优先", exact=True
    ).click()
    page.wait_for_url(lambda url: "sort" not in parse_qs(urlsplit(url).query))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_empty_favorites_keep_controls_and_table_mode_exposes_organization(ui_page):
    page, load = ui_page
    load(
        "pages/project/projects_list.html",
        path="/projects?favorite=true",
        favorite_filter=True,
        projects=[],
        total=0,
    )
    expect(page.locator(".ant-empty-description:visible")).to_have_text(
        "还没有收藏的项目"
    )
    expect(page.get_by_role("link", name="查看全部", exact=True)).to_have_attribute(
        "href", "/projects"
    )
    load("pages/project/projects_list.html")
    page.get_by_role("button", name="列表", exact=True).click()
    page.locator(".desktop-projects").get_by_role(
        "button", name="整理项目", exact=True
    ).click()
    expect(page.get_by_role("menuitem", name="收藏项目", exact=True)).to_be_visible()
    expect(page.get_by_role("menuitem", name="置顶项目", exact=True)).to_be_visible()


def test_dashboard_refresh_failure_keeps_confirmed_flags_and_creation_draft(ui_page):
    page, load = ui_page
    load("pages/project/project_dashboard.html", path="/dashboard")
    field = page.get_by_role("textbox", name="PPT 主题", exact=True)
    field.fill("尚未提交的主题")
    writes = []

    def save(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            json={"status": "success", "is_favorite": True, "is_pinned": False}
        )

    page.route("**/api/projects/*/library-preferences", save)
    page.route(
        "**/dashboard", lambda route: route.fulfill(status=503, body="unavailable")
    )
    page.get_by_role("button", name="整理项目", exact=True).click()
    page.get_by_role("menuitem", name="收藏项目", exact=True).click()
    expect(
        page.get_by_text(
            "整理已保存，项目列表暂未刷新。请刷新页面查看完整排序。", exact=True
        )
    ).to_be_visible()
    expect(page.get_by_label("已收藏", exact=True)).to_be_visible()
    expect(field).to_have_value("尚未提交的主题")
    assert writes == [{"is_favorite": True}]
