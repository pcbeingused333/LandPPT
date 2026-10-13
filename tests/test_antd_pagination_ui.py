"""Large catalogues retain usable pagination within narrow viewports."""

from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_images_ui import image_api
from test_antd_templates_ui import template_api, management
from test_antd_admin_management_ui import USERS


@pytest.mark.parametrize("width", [320, 390, 600, 1024])
@pytest.mark.parametrize("page_count", [5, 100])
@pytest.mark.parametrize(
    "scene", ["projects", "templates", "packages", "images", "users"]
)
def test_large_page_counts_fit_and_next_page_remains_clickable(
    ui_page, width, page_count, scene
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=844))
    if scene == "projects":
        load(
            "pages/project/projects_list.html",
            path="/projects?search=report&status=completed",
            total=page_count * 20,
            search_query="report",
            status_filter="completed",
        )
    elif scene in {"templates", "packages"}:
        state = template_api(page)
        state["total"] = page_count * 6
        if scene == "packages":
            state["packages"] = [
                {
                    **state["packages"][0],
                    "id": index + 100,
                    "template_name": f"模板包 {index}",
                }
                for index in range(page_count * 6)
            ]
        management(page, load, "packages" if scene == "packages" else "regular")
    elif scene == "images":
        state = image_api(page)
        state["total"] = page_count * 20
        load("pages/image/image_gallery.html", path="/image-gallery")
    else:

        def users(route):
            page_number = int(
                parse_qs(urlsplit(route.request.url).query).get("page", [1])[0]
            )
            route.fulfill(
                json={"users": USERS, "total": page_count * 20, "page": page_number}
            )

        page.route("**/admin/api/users?*", users)
        load("pages/admin/users.html", path="/admin/users")

    pagination = page.locator(".projects-pagination .ant-pagination")
    expect(pagination.locator(".ant-pagination-item").first).to_be_visible()
    expect(pagination).to_contain_text(str(page_count))
    pagination.scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
    for item in pagination.locator("li").filter(visible=True).all():
        box = item.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    next_page = pagination.locator(".ant-pagination-next button")
    next_page.scroll_into_view_if_needed()
    if width <= 600:
        assert next_page.bounding_box()["height"] >= 44
    next_page.click()
    if scene == "projects":
        page.wait_for_url(
            lambda url: parse_qs(urlsplit(url).query).get("page") == ["2"]
        )
        query = parse_qs(urlsplit(page.url).query)
        assert query["search"] == ["report"] and query["status"] == ["completed"]
    else:
        expect(pagination.locator(".ant-pagination-item-active")).to_have_text("2")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
