"""Real project cards keep a stable fallback while authenticated thumbnails load."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, detail_project, ui_page  # noqa: F401

COVER = "/api/projects/ui-detail/cover?v=" + "a" * 64
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#17263e"/><text x="40" y="160" fill="white" font-size="40">Saved first slide</text></svg>'


def project_values(project):
    return dict(project, updated_at=project["created_at"], cover_url=COVER)


@pytest.mark.parametrize("template", ["project_dashboard", "projects_list"])
@pytest.mark.parametrize("width", [1440, 390, 320])
def test_saved_cover_keeps_ratio_links_actions_and_responsive_bounds(
    ui_page, detail_project, template, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    writes, errors, requests = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request", lambda req: writes.append(req.url) if req.method != "GET" else None
    )

    def cover(route):
        requests.append(route.request.url)
        route.fulfill(body=SVG, content_type="image/svg+xml")

    page.route("**/api/projects/*/cover?*", cover)
    project = project_values(detail_project)
    load(
        f"pages/project/{template}.html", projects=[project], recent_projects=[project]
    )
    link = page.locator(".project-cover-link:visible")
    link.scroll_into_view_if_needed()
    expect(link.locator(".project-cover--loaded")).to_be_visible()
    image = link.locator("img")
    expect(image).to_have_attribute("src", COVER)
    assert image.evaluate("e => e.complete && e.naturalWidth === 640")
    bounds = image.bounding_box()
    assert abs(bounds["width"] / bounds["height"] - 16 / 9) < 0.02
    assert link.get_attribute("href") == "/projects/ui-detail"
    assert link.get_attribute("aria-label") == "打开项目 " + project["title"]
    expect(
        page.get_by_role("button", name="重命名", exact=True).filter(visible=True)
    ).to_be_visible()
    assert len(requests) == 1 and not errors and not writes
    assert page.locator("iframe").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    if template == "projects_list":
        page.get_by_role("button", name="列表", exact=True).click()
        expect(link).to_have_count(0)
        page.get_by_role("button", name="封面", exact=True).click()
        expect(link).to_have_count(1)
        assert len(requests) == 1


@pytest.mark.parametrize("status", [204, 404, 409, 503])
def test_cover_failure_keeps_title_and_card_actions_without_error_dialog(
    ui_page, detail_project, status
):
    page, load = ui_page
    page.route(
        "**/api/projects/*/cover?*", lambda route: route.fulfill(status=status, body="")
    )
    project = project_values(detail_project)
    load("pages/project/projects_list.html", projects=[project])
    link = page.locator(".project-cover-link:visible")
    link.scroll_into_view_if_needed()
    expect(link.locator("img")).to_have_count(0)
    expect(link.locator(".project-title-cover strong")).to_have_text(project["title"])
    assert page.get_by_role("dialog").count() == 0
    assert page.locator(".ant-message-notice").count() == 0
    expect(
        page.get_by_role("button", name="重命名", exact=True).filter(visible=True)
    ).to_be_enabled()


def test_loading_does_not_replace_title_until_image_arrives_or_shift_card(
    ui_page, detail_project
):
    page, load = ui_page
    pending, state = [], {"pause": False}

    def cover(route):
        if state["pause"]:
            pending.append(route)
        else:
            route.fulfill(status=404, body="")

    page.route("**/api/projects/*/cover?*", cover)
    load("pages/project/projects_list.html", projects=[project_values(detail_project)])
    state["pause"] = True
    page.reload(wait_until="domcontentloaded")
    link = page.locator(".project-cover-link:visible")
    link.scroll_into_view_if_needed()
    expect(link.locator("img")).to_have_count(1)
    before = link.bounding_box()
    assert not link.locator(".project-cover--loaded").count()
    expect(link.locator(".project-title-cover strong")).to_have_text(
        detail_project["title"]
    )
    assert len(pending) == 1
    pending[0].fulfill(body=SVG, content_type="image/svg+xml")
    expect(link.locator(".project-cover--loaded")).to_be_visible()
    after = link.bounding_box()
    assert before == after


def test_draft_without_first_slide_uses_title_without_thumbnail_requests(
    ui_page, detail_project
):
    page, load = ui_page
    requests = []
    page.on(
        "request",
        lambda req: requests.append(req.url) if "/cover?" in req.url else None,
    )
    project = dict(project_values(detail_project), cover_url=None, status="draft")
    load("pages/project/projects_list.html", projects=[project])
    expect(
        page.locator(".project-cover-link:visible .project-title-cover")
    ).to_be_visible()
    assert not page.locator(".project-cover-image").count() and not requests
