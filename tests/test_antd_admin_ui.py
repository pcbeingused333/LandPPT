"""Admin mail/OAuth workflows against production assets, without external writes."""

import pytest

from test_app_ui import browser, ui_page  # noqa: F401

MAIL = dict(
    email_provider="smtp",
    smtp_host="smtp.example.invalid",
    smtp_port=465,
    smtp_user="sender@example.invalid",
    smtp_password="smtp-fixture-secret",
    smtp_use_ssl=True,
    smtp_from_email="",
    smtp_from_name="LandPPT",
    resend_api_key="resend-fixture-secret",
    resend_from_email="resend@example.invalid",
    resend_from_name="LandPPT",
)
OAUTH = dict(
    github=dict(
        enabled=True,
        client_id="github-fixture",
        client_secret="github-fixture-secret",
        callback_url="https://example.invalid/auth/github/callback",
        callback_use_request_host=True,
    ),
    linuxdo=dict(
        enabled=False,
        client_id="linuxdo-fixture",
        client_secret="linuxdo-fixture-secret",
        callback_url="",
    ),
)


def admin(page, load, section, config=None, **values):
    reads, writes = [], []

    def api(route):
        if route.request.method == "GET":
            reads.append(route.request.url)
            route.fulfill(
                json={
                    "success": True,
                    "config": (
                        config
                        if config is not None
                        else MAIL if section == "smtp" else OAUTH
                    ),
                }
            )
        else:
            writes.append((route.request.url, route.request.post_data_json))
            route.fulfill(json={"success": True, "message": "操作完成"})

    page.route(f"**/admin/api/{section}**", api)
    load(f"pages/admin/{section}.html", path=f"/admin/{section}", **values)
    page.get_by_role(
        "heading",
        name="OAuth 设置" if section == "oauth" else "邮件服务设置",
        exact=True,
    ).wait_for()
    return reads, writes


@pytest.mark.parametrize("section", ["oauth", "smtp"])
def test_admin_config_saves_original_payload_and_retains_failed_edits(ui_page, section):
    page, load = ui_page
    reads, unused = admin(page, load, section)
    writes = []

    def save(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            status=500 if len(writes) == 1 else 200,
            json=(
                {"detail": "配置暂时无法保存"}
                if len(writes) == 1
                else {"success": True, "message": "配置已保存"}
            ),
        )

    page.route(f"**/admin/api/{section}", save)
    field = page.locator("#github_client_id" if section == "oauth" else "#smtp_host")
    field.fill("changed-fixture")
    button = page.get_by_role(
        "button", name="保存设置" if section == "oauth" else "保存邮件设置", exact=True
    )
    button.click()
    page.get_by_text("配置暂时无法保存", exact=True).wait_for()
    assert field.input_value() == "changed-fixture"
    button.click()
    page.get_by_text("配置已保存", exact=True).wait_for()
    expected = (
        {**MAIL, "smtp_host": "changed-fixture"}
        if section == "smtp"
        else {**OAUTH, "github": {**OAUTH["github"], "client_id": "changed-fixture"}}
    )
    assert writes == [expected] * 2


@pytest.mark.parametrize("provider", ["smtp", "resend"])
def test_mail_switch_and_test_send_preserve_other_provider_credentials(
    ui_page, provider
):
    page, load = ui_page
    reads, writes = admin(page, load, "smtp")
    page.get_by_role(
        "radio", name="SMTP" if provider == "smtp" else "Resend", exact=True
    ).check()
    page.get_by_label("测试收件邮箱", exact=True).fill("test@example.invalid")
    page.get_by_label("邮件主题（可选）", exact=True).fill("UI fixture")
    page.get_by_label("邮件内容（可选，支持 HTML）", exact=True).fill("<b>fixture</b>")
    page.get_by_role("button", name="发送测试邮件", exact=True).click()
    page.locator(".admin-test-result").get_by_text("操作完成", exact=True).wait_for()
    assert writes == [
        (
            "http://ui.test/admin/api/smtp/test",
            {
                **MAIL,
                "email_provider": provider,
                "test_email": "test@example.invalid",
                "test_subject": "UI fixture",
                "test_content": "<b>fixture</b>",
            },
        )
    ]


def test_invite_test_uses_saved_mail_and_original_channel_payload(ui_page):
    page, load = ui_page
    reads, writes = admin(page, load, "smtp")
    page.get_by_label("收件邮箱", exact=True).fill(
        "one@example.invalid; two@example.invalid"
    )
    page.get_by_label("有效天数（可选）", exact=True).fill("7")
    page.get_by_role("button", name="生成邀请码并发送测试邮件", exact=True).click()
    page.locator(".admin-test-result").get_by_text("操作完成", exact=True).wait_for()
    assert writes == [
        (
            "http://ui.test/admin/api/smtp/test-invite",
            {
                "test_emails": "one@example.invalid; two@example.invalid",
                "channel": "universal",
                "expires_in_days": 7,
            },
        )
    ]


def test_admin_initial_read_does_not_overwrite_edited_fields(ui_page):
    page, load = ui_page
    page.add_init_script(
        """const originalFetch=window.fetch;window.fetch=(url,options)=>url==='/admin/api/oauth'&&(!options||options.method==='GET')?new Promise(resolve=>window.releaseConfig=data=>resolve(new Response(JSON.stringify(data)))):originalFetch(url,options);"""
    )
    load("pages/admin/oauth.html", path="/admin/oauth")
    page.locator("#github_client_id").fill("typed-while-loading")
    assert page.get_by_role("button", name="保存设置", exact=True).is_disabled()
    page.evaluate("data=>window.releaseConfig({success:true,config:data})", OAUTH)
    page.wait_for_function(
        "!document.querySelector('.settings-savebar .ant-btn-primary').disabled"
    )
    assert page.locator("#github_client_id").input_value() == "typed-while-loading"
    assert (
        page.locator("#github_client_secret").input_value() == "github-fixture-secret"
    )


def test_admin_entry_and_read_requests_execute_once(ui_page):
    page, load = ui_page
    entries = []
    page.on(
        "request",
        lambda request: (
            entries.append(request.url)
            if request.url.split("?")[0].endswith("/static/antd/app.js")
            else None
        ),
    )
    reads, writes = admin(page, load, "oauth")
    assert len(entries) == 1
    assert entries[0].split("?")[0] == "http://ui.test/static/antd/app.js"
    assert reads == ["http://ui.test/admin/api/oauth"]
    assert not writes


@pytest.mark.parametrize("section", ["smtp", "oauth"])
def test_admin_read_error_retries_and_blocks_save_of_unknown_credentials(
    ui_page, section
):
    page, load = ui_page
    reads = []

    def read(route):
        reads.append(route.request.url)
        route.fulfill(
            status=500 if len(reads) == 1 else 200,
            json=(
                {"detail": "读取失败"}
                if len(reads) == 1
                else {"success": True, "config": MAIL if section == "smtp" else OAUTH}
            ),
        )

    page.route(f"**/admin/api/{section}", read)
    load(f"pages/admin/{section}.html", path=f"/admin/{section}")
    page.get_by_text("读取失败", exact=True).wait_for()
    button = page.get_by_role(
        "button", name="保存邮件设置" if section == "smtp" else "保存设置", exact=True
    )
    assert button.is_disabled()
    page.get_by_role("button", name="重试", exact=True).click()
    page.wait_for_function(
        "!document.querySelector('.settings-savebar .ant-btn-primary').disabled"
    )
    assert len(reads) == 2


def test_admin_save_prevents_multiple_pending_posts(ui_page):
    page, load = ui_page
    admin(page, load, "oauth")
    held = []
    page.route("**/admin/api/oauth", lambda route: held.append(route))
    page.get_by_role("button", name="保存设置", exact=True).evaluate(
        "e=>{e.click();e.click()}"
    )
    page.wait_for_timeout(100)
    assert len(held) == 1
    held[0].fulfill(json={"success": True, "message": "配置已保存"})
    page.get_by_text("配置已保存", exact=True).wait_for()


@pytest.mark.parametrize("section", ["smtp", "oauth"])
def test_admin_pages_do_not_request_credentials_for_non_admin_users(ui_page, section):
    page, load = ui_page
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    load(
        f"pages/admin/{section}.html",
        path=f"/admin/{section}",
        user=dict(username="member", is_admin=False),
    )
    page.get_by_text("需要管理员权限", exact=True).wait_for()
    assert not [url for url in requests if "/admin/api/" in url]


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
)
@pytest.mark.parametrize("scene", ["smtp", "resend", "oauth"])
def test_admin_settings_keep_navigation_and_save_reachable(
    ui_page, width, height, scene
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    admin(page, load, "oauth" if scene == "oauth" else "smtp", credits_enabled=False)
    if scene == "resend":
        page.get_by_role("radio", name="Resend", exact=True).check()
    assert page.locator('.admin-navigation a[href="/admin/credits"]').count() == 0
    assert page.locator('.admin-navigation a[aria-current="page"]').count() == 1
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    page.locator(".admin-page input:visible").last.scroll_into_view_if_needed()
    button = page.locator(".settings-savebar .ant-btn-primary")
    box = button.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert button.evaluate(
        "e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
    )
    assert not errors


@pytest.mark.parametrize("provider", ["smtp", "resend"])
def test_mail_save_validates_active_provider_and_preserves_hidden_values(
    ui_page, provider
):
    page, load = ui_page
    config = {
        **MAIL,
        "email_provider": provider,
        (
            "resend_from_email" if provider == "smtp" else "smtp_from_email"
        ): "previously-saved-value",
    }
    reads, writes = admin(page, load, "smtp", config=config)
    page.get_by_role("button", name="保存邮件设置", exact=True).click()
    page.get_by_text("操作完成", exact=True).wait_for()
    assert writes == [("http://ui.test/admin/api/smtp", config)]
