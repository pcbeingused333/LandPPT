"""Startup parallelism and navigation continuity using the actual built assets."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import STATIC, browser, ui_page  # noqa: F401
from test_antd_navigation_ui import ROUTES, navigation_app, open_navigation

OUT = Path("artifacts/navigation-20261024")


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_startup_has_no_brand_loading_text_and_reads_creation_settings_in_parallel(
    ui_page, width, height
):
    page, _ = ui_page
    page.set_viewport_size({"width": width, "height": height})
    state = navigation_app(page)
    manifest = json.loads((STATIC / "antd/manifest.json").read_text(encoding="utf-8"))
    entry = manifest["src/main.tsx"]["file"]
    waiting = []
    page.route("**/" + entry, lambda route: waiting.append(route))
    page.goto("http://ui.test/dashboard", wait_until="domcontentloaded")
    expect(page.locator(".app-startup")).to_be_visible()
    expect(page.locator("#antdRoot")).to_have_text("")
    expect(page.locator("body")).to_have_css("background-color", "rgb(11, 11, 12)")
    expect(page.locator(".app-startup > span").first).to_have_css("height", "24px")
    assert waiting
    # The authenticated settings read has already started while React is held.
    assert [item["path"] for item in state["reads"]] == ["/dashboard", "/create"]
    preloads = page.locator('link[rel="modulepreload"]').evaluate_all(
        "links=>links.map(link=>new URL(link.href).pathname)"
    )
    assert "/static/antd/" + entry in preloads
    assert "/static/antd/" + manifest["src/pages/dashboard.tsx"]["file"] in preloads
    assert len(preloads) == len(set(preloads))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"startup-{width}.png"))
    for route in waiting:
        route.fulfill(
            body=(STATIC / "antd" / entry).read_bytes(), content_type="text/javascript"
        )
    topic = page.get_by_role("textbox", name="PPT 主题", exact=True)
    expect(topic).to_have_attribute("placeholder", "演示主题，例如：人工智能的未来结局")
    expect(topic).to_have_value("")
    assert sum(item["path"] == "/create" for item in state["reads"]) == 1
    assert not state["errors"]


def test_pending_navigation_keeps_current_content_and_does_not_refetch_sidebar(ui_page):
    page, _ = ui_page
    state = navigation_app(page)
    recent_reads = []

    def recent(route):
        recent_reads.append(route.request.url)
        route.fulfill(json={"projects": []})

    page.route("**/api/projects?**", recent)
    page.goto("http://ui.test/dashboard", wait_until="networkidle")
    topic = page.get_by_role("textbox", name="PPT 主题", exact=True)
    topic.fill("保留我的输入")
    assert len(recent_reads) == 1
    page.evaluate("window.originalHeader=document.querySelector('.app-header')")
    waiting = []
    state["handlers"]["/projects"] = lambda route: waiting.append(route)
    page.locator('.app-sidebar .app-nav a[href="/projects"]').click()
    expect(page.locator("#appMain")).to_have_attribute("aria-busy", "true")
    expect(topic).to_have_value("保留我的输入")
    assert page.evaluate(
        "window.originalHeader===document.querySelector('.app-header')"
    )
    assert len(recent_reads) == 1
    assert waiting
    waiting[0].fulfill(body=state["render"]("/projects"), content_type="text/html")
    expect(
        page.get_by_role("heading", name=ROUTES["/projects"][1], exact=True)
    ).to_be_visible()
    expect(page.locator("#appMain")).to_have_attribute("aria-busy", "false")
    assert len(recent_reads) == 2
    assert page.evaluate(
        "window.originalHeader===document.querySelector('.app-header')"
    )
    open_navigation(page, "/dashboard")
    expect(page.get_by_role("textbox", name="PPT 主题", exact=True)).to_have_value(
        "保留我的输入"
    )
    assert len(recent_reads) == 3
    assert not state["errors"]


def test_cancelling_pending_navigation_does_not_restart_shell_requests(ui_page):
    page, _ = ui_page
    state = navigation_app(page)
    recent_reads = []
    page.route(
        "**/api/projects?**",
        lambda route: (
            recent_reads.append(route.request.url),
            route.fulfill(json={"projects": []}),
        ),
    )
    page.goto("http://ui.test/dashboard", wait_until="networkidle")
    page.evaluate(
        """() => {
        const original=fetch;
        window.fetch=(url,...args)=>new URL(url,location.href).pathname==='/projects'
            ? new Promise(()=>{}) : original(url,...args);
    }"""
    )
    page.locator('.app-sidebar .app-nav a[href="/projects"]').click()
    expect(page.locator("#appMain")).to_have_attribute("aria-busy", "true")
    page.locator('.app-sidebar .app-nav a[href="/dashboard"]').click()
    expect(page.locator("#appMain")).to_have_attribute("aria-busy", "false")
    assert len(recent_reads) == 1
    assert not state["errors"]
