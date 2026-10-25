"""Dark / 可可蛋白 light appearance: header toggle, persistence and shared tokens."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401

LIGHT = "切换到浅色模式（可可蛋白）"
DARK = "切换到深色模式"


def theme(page):
    return page.evaluate("document.documentElement.dataset.theme || 'dark'")


def token(page, name):
    return page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('--lp-{name}').trim()")


def background(page, selector):
    return page.evaluate(f"getComputedStyle(document.querySelector('{selector}')).backgroundColor")


def test_header_toggle_switches_native_tokens_and_ant_components(ui_page):
    page, load = ui_page
    load("pages/project/project_dashboard.html", path="/dashboard")
    toggle = page.get_by_role("button", name=LIGHT)
    expect(toggle).to_have_attribute("aria-pressed", "false")
    assert theme(page) == "dark"
    dark_card = background(page, ".ant-card")
    toggle.click()
    expect(page.get_by_role("button", name=DARK)).to_have_attribute("aria-pressed", "true")
    assert theme(page) == "light"
    assert token(page, "bg") == "#f3ebe1" and token(page, "primary") == "#6b4430"
    assert page.evaluate("localStorage.getItem('landppt-theme')") == "light"
    # Ant tokens are rebuilt from the same palette, so containers follow the native surface.
    expect(page.locator(".ant-card").first).not_to_have_css("background-color", dark_card)
    assert background(page, ".ant-card") == "rgb(255, 250, 244)"
    page.get_by_role("button", name=DARK).click()
    assert theme(page) == "dark"
    assert page.evaluate("localStorage.getItem('landppt-theme')") == "dark"


@pytest.mark.parametrize("template,path", [
    ("pages/project/project_dashboard.html", "/dashboard"),
    ("pages/auth/login.html", "/auth/login"),
])
def test_saved_light_appearance_applies_before_the_app_mounts(ui_page, template, path):
    page, load = ui_page
    page.add_init_script("localStorage.setItem('landppt-theme', 'light')")
    page.add_init_script(
        "document.addEventListener('DOMContentLoaded', () => { window.themeAtReady = document.documentElement.dataset.theme || 'dark'; })"
    )
    load(template, path=path)
    assert page.evaluate("window.themeAtReady") == "light"
    # App pages paint the elevated cream, auth pages the base cream.
    assert background(page, "body") in ("rgb(243, 235, 225)", "rgb(247, 239, 229)")


@pytest.mark.parametrize("width", [390, 320])
def test_toggle_fits_the_mobile_header(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=700))
    load("pages/project/project_dashboard.html", path="/dashboard")
    toggle = page.get_by_role("button", name=LIGHT)
    expect(toggle).to_be_visible()
    box = toggle.bounding_box()
    assert box["height"] >= 32 and box["x"] + box["width"] <= width
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
