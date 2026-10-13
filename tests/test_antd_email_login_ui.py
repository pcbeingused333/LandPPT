"""The restored native login form accepts usernames and email addresses."""

from urllib.parse import parse_qs

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
@pytest.mark.parametrize("identifier", ["demo-user", " Demo+Tag@Example.COM "])
def test_username_and_email_submit_using_the_existing_form_contract(
    ui_page, width, height, identifier
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    writes = []

    def capture(route):
        if route.request.method == "POST":
            assert route.request.resource_type == "document"
            writes.append(parse_qs(route.request.post_data))
            route.fulfill(
                body='<meta charset="utf-8"><h1>登录成功</h1>', content_type="text/html"
            )
        else:
            route.fallback()

    page.route("**/auth/login", capture)
    load("pages/auth/login.html", path="/auth/login", user=None)
    form = page.locator("#loginFormElement")
    account = form.get_by_label("用户名或邮箱", exact=True)
    expect(account).to_have_attribute("type", "text")
    expect(account).to_have_attribute("name", "username")
    expect(account).to_have_attribute("placeholder", "输入用户名或邮箱")
    account.fill(identifier)
    form.get_by_label("密码", exact=True).fill("test-password")
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="登录成功", exact=True).wait_for()
    assert writes == [{"username": [identifier], "password": ["test-password"]}]


def test_email_login_failure_keeps_account_and_does_not_rename_registration_field(
    ui_page,
):
    page, load = ui_page
    load(
        "pages/auth/login.html",
        path="/auth/login",
        user=None,
        username="Wrong@Example.COM",
        error="账号或密码错误",
        register_username="register-user",
    )
    form = page.locator("#loginFormElement")
    expect(form.get_by_label("用户名或邮箱", exact=True)).to_have_value(
        "Wrong@Example.COM"
    )
    expect(form.get_by_label("密码", exact=True)).to_have_value("")
    expect(page.get_by_text("账号或密码错误", exact=True)).to_be_visible()
    page.get_by_role("tab", name="注册", exact=True).click()
    expect(
        page.locator("#registerFormElement").get_by_label("用户名", exact=True)
    ).to_have_value("register-user")
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
