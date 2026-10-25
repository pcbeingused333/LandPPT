"""Authenticated generation pages show the account menu and keep role boundaries."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_home_generator_ui import ORIGINAL, setup_workspace

OUT = Path("artifacts/generator-auth-20261025")


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("width", [1440, 390, 320])
def test_generation_shell_shows_current_account_and_no_login_link(
    ui_page, width, admin
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    user = dict(
        username="generator-admin" if admin else "generator-user", is_admin=admin
    )

    def authenticated_load(template, **values):
        return load(template, user=user, **values)

    state = setup_workspace(page, authenticated_load, mode="global", completed=True)
    data = json.loads(page.locator("#antdData").text_content())
    assert data["user"] == user
    expect(page.get_by_role("link", name="登录", exact=True)).to_have_count(0)
    account = page.locator(".app-header").get_by_role(
        "button", name="账户菜单", exact=True
    )
    expect(account).to_be_visible()
    expect(page.locator("#navNotificationBell")).to_be_visible()
    account.click()
    expect(page.get_by_role("menuitem", name="个人资料", exact=True)).to_be_visible()
    expect(page.get_by_role("menuitem", name="管理后台", exact=True)).to_have_count(
        1 if admin else 0
    )
    page.keyboard.press("Escape")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.evaluate("testStreams.length") == 0
    assert all(
        frame.get_attribute("srcdoc") == ORIGINAL
        for frame in page.locator(".slide-preview iframe").all()
    )
    assert not state["writes"] and not errors
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(OUT / f"account-{'admin' if admin else 'user'}-{width}.png"),
        animations="disabled",
    )
