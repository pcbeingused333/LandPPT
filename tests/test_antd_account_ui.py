"""Account/auth contracts against actual Jinja templates and built UI assets."""

import re
from urllib.parse import parse_qs, urlsplit

import pytest

from test_app_ui import browser, ui_page  # noqa: F401


def auth(page, load, mode="login", **values):
    templates = {
        "login": "login",
        "register": "register",
        "reset": "forgot_password",
    }
    paths = {
        "login": "/auth/login",
        "register": "/auth/register",
        "reset": "/auth/forgot-password",
    }
    load(
        f"pages/auth/{templates[mode]}.html",
        path=paths[mode],
        user=None,
        invite_code_required_for_registration=False,
        **values,
    )
    page.get_by_role(
        "heading",
        name={
            "login": (
                "创建账户" if values.get("active_tab") == "register" else "欢迎回来"
            ),
            "register": "创建账户",
            "reset": "重置密码",
        }[mode],
        exact=True,
    ).wait_for()


def profile(page, load, tab="overview", **values):
    load("pages/account/profile.html", path=f"/auth/profile#{tab}", **values)
    page.get_by_role("heading", name="个人资料", exact=True).wait_for()


def native_posts(page, path):
    writes = []

    def capture(route):
        if route.request.method == "POST":
            writes.append(parse_qs(route.request.post_data, keep_blank_values=True))
            assert route.request.resource_type == "document"
            assert route.request.headers["content-type"].startswith(
                "application/x-www-form-urlencoded"
            )
            route.fulfill(
                body='<meta charset="utf-8"><h1>表单已提交</h1>',
                content_type="text/html",
            )
        else:
            route.fallback()

    page.route(f"**{path}", capture)
    return writes


@pytest.mark.parametrize("mode", ["login", "register", "reset", "password"])
def test_account_forms_keep_native_post_fields_and_validate_confirmation(ui_page, mode):
    page, load = ui_page
    paths = {
        "login": "/auth/login",
        "register": "/auth/register",
        "reset": "/auth/reset-password",
        "password": "/auth/change-password",
    }
    writes = native_posts(page, paths[mode])
    if mode == "password":
        profile(page, load, "security")
        page.get_by_label("当前密码", exact=True).fill("old-secret")
        page.get_by_label("新密码", exact=True).fill("new-secret")
        page.get_by_label("确认新密码", exact=True).fill("mismatch")
        submit = page.get_by_role("button", name="修改密码", exact=True)
        expected = {
            "current_password": ["old-secret"],
            "new_password": ["new-secret"],
            "confirm_password": ["new-secret"],
        }
    elif mode == "login":
        auth(page, load)
        page.locator("#loginFormElement").get_by_label("用户名或邮箱", exact=True).fill("demo-user")
        page.locator("#loginFormElement").get_by_label("密码", exact=True).fill("new-secret")
        submit = page.locator("#loginFormElement").get_by_role(
            "button", name="登录", exact=True
        )
        expected = {"username": ["demo-user"], "password": ["new-secret"]}
    else:
        auth(page, load, mode, username="demo-user", email="demo@example.invalid")
        page.get_by_label("验证码", exact=True).fill("123456")
        page.get_by_label("密码" if mode == "register" else "新密码", exact=True).fill(
            "new-secret"
        )
        page.get_by_label(
            "确认密码" if mode == "register" else "确认新密码", exact=True
        ).fill("mismatch")
        submit = page.get_by_role(
            "button", name="注册" if mode == "register" else "重置密码", exact=True
        )
        expected = {
            "email": ["demo@example.invalid"],
            "code": ["123456"],
            "confirm_password": ["new-secret"],
            "turnstile_token": [""],
            "password" if mode == "register" else "new_password": ["new-secret"],
        }
        if mode == "register":
            expected.update(username=["demo-user"], invite_code=[""], ui=["standalone"])
    if mode != "login":
        submit.click()
        page.get_by_text("两次密码输入不一致", exact=True).wait_for()
        assert not writes
        page.get_by_label(
            "确认密码" if mode == "register" else "确认新密码", exact=True
        ).fill("new-secret")
    submit.click()
    page.get_by_role("heading", name="表单已提交").wait_for()
    assert writes == [expected]


def test_combined_registration_keeps_ui_context_and_failure_values(ui_page):
    page, load = ui_page
    writes = native_posts(page, "/auth/register")
    auth(
        page,
        load,
        active_tab="register",
        register_error="注册暂时失败",
        register_email="demo@example.invalid",
        register_username="demo-user",
        register_invite_code="invite-1",
    )
    page.get_by_text("注册暂时失败", exact=True).wait_for()
    form = page.locator("#registerFormElement")
    form.get_by_label("验证码", exact=True).fill("123456")
    form.get_by_label("密码", exact=True).fill("new-secret")
    form.get_by_label("确认密码", exact=True).fill("new-secret")
    page.get_by_role("button", name="注册", exact=True).click()
    page.get_by_role("heading", name="表单已提交").wait_for()
    assert writes[0]["ui"] == ["login"]
    assert writes[0]["invite_code"] == ["invite-1"]
    assert writes[0]["email"] == ["demo@example.invalid"]


def test_combined_auth_tabs_keep_unique_input_ids_and_independent_values(ui_page):
    page, load = ui_page
    auth(
        page,
        load,
        active_tab="register",
        register_username="register-user",
        register_email="demo@example.invalid",
    )
    page.get_by_role("tab", name="登录", exact=True).click()
    page.locator("#loginFormElement").get_by_label("用户名或邮箱", exact=True).fill(
        "login-user"
    )
    ids = page.locator(".auth-shell input[id]").evaluate_all(
        "elements => elements.map(e=>e.id)"
    )
    assert len(ids) == len(set(ids))
    page.get_by_role("tab", name="注册", exact=True).click()
    assert (
        page.locator("#registerFormElement").get_by_label("用户名", exact=True).input_value()
        == "register-user"
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_oauth_visibility_tracks_server_provider_flags(ui_page, enabled):
    page, load = ui_page
    auth(page, load, github_oauth_enabled=enabled, linuxdo_oauth_enabled=enabled)
    assert page.locator('a[href="/auth/github/login"]:visible').count() == enabled
    assert page.locator('a[href="/auth/linuxdo/login"]:visible').count() == enabled


@pytest.mark.parametrize("required", [True, False])
def test_oauth_registration_keeps_optional_and_required_invites(ui_page, required):
    page, load = ui_page
    load(
        "pages/auth/register.html",
        path="/auth/register",
        user=None,
        github_oauth_enabled=True,
        invite_code_required_for_registration=required,
    )
    link = page.get_by_role("link", name="GitHub 注册", exact=True)
    if required:
        link.click()
        page.get_by_text("请先填写邀请码，再选择注册渠道。", exact=True).wait_for()
        assert urlsplit(page.url).path == "/auth/register"
        page.get_by_label("邀请码", exact=True).fill("team + &")
    link.click()
    page.wait_for_url("**/auth/github/login*")
    assert parse_qs(urlsplit(page.url).query) == (
        {"invite_code": ["team + &"], "redirect_url": ["/dashboard"]}
        if required else {"redirect_url": ["/dashboard"]}
    )


def test_registration_closed_exposes_no_registration_or_oauth_form(ui_page):
    page, load = ui_page
    load(
        "pages/auth/register.html",
        path="/auth/register",
        user=None,
        registration_enabled=False,
        github_oauth_enabled=True,
    )
    page.get_by_text("注册已关闭", exact=True).wait_for()
    assert page.locator(".auth-shell form").count() == 0
    assert page.locator('a[href="/auth/github/login"]').count() == 0


def test_code_send_failure_retains_email_and_retry_locks_countdown(ui_page):
    page, load = ui_page
    writes = []

    def send(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            json={"success": len(writes) > 1, "message": "验证码暂时无法发送"}
        )

    page.route("**/auth/api/send-code", send)
    auth(page, load, "register")
    page.get_by_label("邮箱地址", exact=True).fill("demo@example.invalid")
    page.get_by_role("button", name="发送验证码", exact=True).click()
    page.get_by_text("验证码暂时无法发送", exact=True).wait_for()
    assert (
        page.get_by_label("邮箱地址", exact=True).input_value()
        == "demo@example.invalid"
    )
    assert page.locator(".js-after-code").bounding_box()["height"] == 0
    assert page.get_by_label("用户名", exact=True).is_disabled()
    page.get_by_role("button", name="发送验证码", exact=True).click()
    page.get_by_label("用户名", exact=True).wait_for()
    assert page.get_by_role("button", name=re.compile(r"^\d+s$")).is_disabled()
    assert (
        writes
        == [
            {
                "email": "demo@example.invalid",
                "code_type": "register",
                "invite_code": "",
                "turnstile_token": "",
            }
        ]
        * 2
    )


@pytest.mark.parametrize("mode", ["register", "reset"])
def test_code_send_prevents_duplicate_pending_requests(ui_page, mode):
    page, load = ui_page
    held = []
    page.route("**/auth/api/send-code", lambda route: held.append(route))
    auth(page, load, mode)
    page.get_by_label("邮箱地址", exact=True).fill("demo@example.invalid")
    page.get_by_role("button", name="发送验证码", exact=True).evaluate(
        "e => {e.click(); e.click()}"
    )
    page.wait_for_timeout(100)
    assert len(held) == 1
    expected = {
        "email": "demo@example.invalid",
        "code_type": "register" if mode == "register" else "reset",
        "turnstile_token": "",
    }
    if mode == "register":
        expected["invite_code"] = ""
    assert held[0].request.post_data_json == expected
    held[0].fulfill(json={"success": True})
    page.get_by_text("验证码已发送到您的邮箱，请查收" + ("。" if mode == "register" else ""), exact=True).wait_for()


@pytest.mark.parametrize("mode", ["register", "reset"])
def test_code_countdown_ends_and_allows_another_send(ui_page, mode):
    page, load = ui_page
    writes = []
    page.clock.install()
    page.route(
        "**/auth/api/send-code",
        lambda route: (
            writes.append(route.request.post_data_json),
            route.fulfill(json={"success": True}),
        ),
    )
    auth(page, load, mode)
    page.get_by_label("邮箱地址", exact=True).fill("demo@example.invalid")
    page.get_by_role("button", name="发送验证码", exact=True).click()
    page.get_by_text("验证码已发送到您的邮箱，请查收" + ("。" if mode == "register" else ""), exact=True).wait_for()
    assert page.get_by_role("button", name=re.compile(r"^\d+s$" if mode == "register" else r"\d+s 后重发")).is_disabled()
    page.clock.fast_forward(61000)
    page.get_by_role("button", name="发送验证码", exact=True).click()
    page.wait_for_timeout(100)
    assert len(writes) == 2


TURNSTILE_STUB = """window.challengeOptions=[];window.removedChallenges=[];
window.turnstile={render:(node,options)=>{window.challengeOptions.push(options);
node.textContent='测试人机验证';return String(window.challengeOptions.length)},
remove:id=>window.removedChallenges.push(id)};"""


def test_turnstile_only_mounts_for_active_registration_and_expires_token(ui_page):
    page, load = ui_page
    page.add_init_script(TURNSTILE_STUB)
    writes = []
    page.route(
        "**/auth/api/send-code",
        lambda route: (
            writes.append(route.request.post_data_json),
            route.fulfill(json={"success": True}),
        ),
    )
    auth(page, load, turnstile_enabled=True, turnstile_site_key="public-test-site")
    assert page.evaluate("window.challengeOptions.length") == 0
    page.get_by_role("tab", name="注册", exact=True).click()
    page.get_by_text("测试人机验证", exact=True).wait_for()
    page.get_by_label("邮箱地址", exact=True).fill("demo@example.invalid")
    page.get_by_role("button", name="发送验证码", exact=True).click()
    page.get_by_text("请先完成人机验证，通过后才可发送验证码。", exact=True).wait_for()
    assert not writes
    page.evaluate(
        "window.challengeOptions[0].callback('expired-test-token'); window.challengeOptions[0]['expired-callback']()"
    )
    page.get_by_role("button", name="发送验证码", exact=True).click()
    assert not writes
    page.evaluate("window.challengeOptions[0].callback('valid-test-token')")
    page.get_by_role("button", name="发送验证码", exact=True).click()
    page.get_by_text("验证码已发送到您的邮箱，请查收。", exact=True).wait_for()
    assert writes[0]["turnstile_token"] == "valid-test-token"
    page.get_by_role("tab", name="登录", exact=True).click()
    assert page.evaluate("window.removedChallenges") == ["1"]
    page.get_by_role("tab", name="注册", exact=True).click()
    page.wait_for_function("window.challengeOptions.length === 2")
    page.evaluate("window.challengeOptions[0].callback('late-token-from-removed-widget')")
    assert page.locator('input[name="turnstile_token"]').input_value() == ""
    page.evaluate("window.challengeOptions[1].callback('new-widget-token')")
    assert page.locator('input[name="turnstile_token"]').input_value() == "new-widget-token"


@pytest.mark.parametrize("mode", ["register", "reset"])
def test_turnstile_script_failure_can_retry_without_bypassing_verification(ui_page, mode):
    page, load = ui_page
    scripts = []

    def script(route):
        scripts.append(route.request.url)
        if len(scripts) == 1:
            route.abort()
        else:
            route.fulfill(body=TURNSTILE_STUB, content_type="text/javascript")

    page.route(
        "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit", script
    )
    auth(
        page,
        load,
        mode,
        turnstile_enabled=True,
        turnstile_site_key="public-test-site",
    )
    page.get_by_text(re.compile(r"人机验证加载失败")).wait_for()
    page.get_by_role("button", name="重试", exact=True).click()
    page.get_by_text("测试人机验证", exact=True).wait_for()
    assert len(scripts) == 2
    assert page.evaluate("window.challengeOptions[0]['response-field']") is False


@pytest.mark.parametrize("enabled", [True, False])
def test_profile_credit_visibility_and_public_payload(ui_page, enabled):
    page, load = ui_page
    reads = []
    page.on("request", lambda request: reads.append(request.url))
    profile(
        page,
        load,
        credits_enabled=enabled,
        user=dict(
            username="demo",
            email="demo@example.invalid",
            is_admin=False,
            password_hash="never-render",
            created_at=1791691830,
        ),
    )
    assert page.get_by_role("tab", name="我的积分").count() == enabled
    assert page.get_by_role("link", name="管理后台", exact=True).count() == 0
    assert "never-render" not in page.content()
    assert not [url for url in reads if "/credits/api/" in url]
    if enabled:
        page.get_by_role("tab", name="我的积分").click()
        page.get_by_role("button", name="立即签到", exact=True).wait_for()
        assert any("/credits/api/checkin-status" in url for url in reads)


def test_api_key_create_failure_retains_values_and_blank_optionals_are_omitted(ui_page):
    page, load = ui_page
    writes = []

    def api(route):
        if route.request.method == "GET":
            route.fulfill(json={"api_keys": []})
        else:
            writes.append(route.request.post_data_json)
            route.fulfill(
                status=500 if len(writes) == 1 else 200,
                json=(
                    {"detail": "创建暂时失败"}
                    if len(writes) == 1
                    else {"api_key": "test-once-only-key", "rotated": False}
                ),
            )

    page.route("**/api/auth/api-keys*", api)
    profile(page, load, "apikeys")
    page.get_by_label("Key 名称", exact=True).fill("automation")
    page.get_by_role("button", name="创建 / 轮换", exact=True).click()
    page.get_by_text("创建暂时失败", exact=True).wait_for()
    assert page.get_by_label("Key 名称", exact=True).input_value() == "automation"
    page.get_by_role("button", name="创建 / 轮换", exact=True).click()
    page.get_by_text("test-once-only-key", exact=True).wait_for()
    assert writes == [{"name": "automation"}] * 2
    page.evaluate(
        "window.copied='';document.execCommand=()=>{window.copied=document.activeElement.value;return true}"
    )
    page.get_by_role("button", name="复制 Key", exact=True).click()
    page.get_by_text("API Key 已复制", exact=True).wait_for()
    assert page.evaluate("window.copied") == "test-once-only-key"


def test_api_key_custom_rotation_and_delete_confirmation_retry(ui_page):
    page, load = ui_page
    writes = []
    deletes = []
    key = dict(
        id=7,
        name="production",
        key_preview="sk-fixture***",
        is_active=True,
        created_at=1791691830,
    )

    def api(route):
        if route.request.method == "GET":
            route.fulfill(json={"api_keys": [key] if len(deletes) < 2 else []})
        elif route.request.method == "DELETE":
            deletes.append(route.request.url)
            route.fulfill(
                status=500 if len(deletes) == 1 else 200,
                json=(
                    {"detail": "删除失败，请重试"}
                    if len(deletes) == 1
                    else {"success": True}
                ),
            )
        else:
            writes.append(route.request.post_data_json)
            route.fulfill(json={"api_key": "custom-key-for-testing", "rotated": True})

    page.route("**/api/auth/api-keys**", api)
    profile(page, load, "apikeys")
    page.get_by_label("Key 名称", exact=True).fill("production")
    page.get_by_label("自定义 Key（可选）", exact=True).fill("custom-key-for-testing")
    page.get_by_label("过期天数（可选）", exact=True).fill("30")
    page.get_by_role("button", name="创建 / 轮换", exact=True).click()
    page.get_by_text("API Key 轮换成功，请立即保存", exact=True).wait_for()
    assert writes == [
        {
            "name": "production",
            "api_key": "custom-key-for-testing",
            "expires_in_days": 30,
        }
    ]
    assert page.get_by_label("自定义 Key（可选）", exact=True).input_value() == ""
    page.get_by_role("button", name="删除 production", exact=True).first.click()
    dialog = page.get_by_role("dialog", name="删除 API Key", exact=True)
    dialog.get_by_role("button", name="取消", exact=True).click()
    assert not deletes
    page.get_by_role("button", name="删除 production", exact=True).first.click()
    dialog.get_by_role("button", name="删除", exact=True).click()
    page.get_by_text("删除失败，请重试", exact=True).wait_for()
    assert dialog.is_visible()
    dialog.get_by_role("button", name="删除", exact=True).click()
    dialog.wait_for(state="hidden")
    assert len(deletes) == 2 and all(
        url.endswith("/api/auth/api-keys/7") for url in deletes
    )


def credit_fixture(page):
    writes = []
    reads = []
    state = {"balance": 120, "checked": False, "fail_redeem": True, "fail_page": False}

    def api(route):
        path = urlsplit(route.request.url).path
        (
            reads.append(route.request.url)
            if route.request.method == "GET"
            else writes.append((path, route.request.post_data_json))
        )
        if path.endswith("checkin-status"):
            result = dict(
                enabled=True,
                already_checked_in=state["checked"],
                reward_preview=5,
                today_reward=5 if state["checked"] else 0,
            )
        elif path.endswith("checkin"):
            state.update(balance=state["balance"] + 5, checked=True)
            result = dict(
                success=True,
                new_balance=state["balance"],
                today_reward=5,
                message="签到成功",
            )
        elif path.endswith("redeem"):
            if state["fail_redeem"]:
                state["fail_redeem"] = False
                result = dict(success=False, message="兑换暂时失败")
            else:
                state["balance"] += 50
                result = dict(
                    success=True, new_balance=state["balance"], message="兑换成功"
                )
        elif path.endswith("balance"):
            result = dict(
                balance=state["balance"], total_consumed=30, total_recharged=150
            )
        elif path.endswith("pricing"):
            result = dict(pricing={"slide": dict(cost=3, description="AI 调用")})
        else:
            number = int(parse_qs(urlsplit(route.request.url).query)["page"][0])
            if number == 2 and state["fail_page"]:
                state["fail_page"] = False
                route.fulfill(status=500, json={"detail": "交易明细加载失败"})
                return
            result = dict(
                total=25,
                transactions=[
                    dict(
                        id=number,
                        created_at=1791691830,
                        transaction_type="recharge",
                        amount=50,
                        balance_after=120,
                        description=f"第 {number} 页充值记录",
                    )
                ],
            )
        route.fulfill(json=result)

    page.route("**/credits/api/**", api)
    return state, writes, reads


def test_credits_checkin_redeem_retry_updates_balance_and_preserves_input(ui_page):
    page, load = ui_page
    state, writes, reads = credit_fixture(page)
    load("pages/account/user_credits.html", path="/credits")
    page.get_by_role("button", name="立即签到", exact=True).click()
    page.get_by_role("button", name="今日已签到", exact=True).wait_for()
    assert page.get_by_role("button", name="今日已签到", exact=True).is_disabled()
    page.get_by_label("兑换码", exact=True).fill("  code-for-testing  ")
    page.get_by_role("button", name="兑换", exact=True).click()
    page.get_by_text("兑换暂时失败", exact=True).wait_for()
    assert (
        page.get_by_label("兑换码", exact=True).input_value() == "  code-for-testing  "
    )
    page.get_by_role("button", name="兑换", exact=True).click()
    page.get_by_text("兑换成功", exact=True).wait_for()
    page.wait_for_function(
        "document.querySelector('.credits-stats .stat-number').textContent==='175'"
    )
    assert page.get_by_label("兑换码", exact=True).input_value() == ""
    assert [payload for path, payload in writes if path.endswith("redeem")] == [
        {"code": "code-for-testing"}
    ] * 2
    assert state["balance"] == 175


def test_credit_pagination_failure_keeps_current_records_and_retries_target_page(
    ui_page,
):
    page, load = ui_page
    state, writes, reads = credit_fixture(page)
    state["fail_page"] = True
    load("pages/account/user_credits.html", path="/credits")
    page.get_by_text("第 1 页充值记录", exact=True).first.wait_for()
    page.locator(".ant-pagination-next button").click()
    page.get_by_text("交易明细加载失败", exact=True).wait_for()
    assert page.get_by_text("第 1 页充值记录", exact=True).first.is_visible()
    assert page.locator(".ant-pagination-item-active").inner_text() == "1"
    page.get_by_role("button", name="重试", exact=True).click()
    page.get_by_text("第 2 页充值记录", exact=True).first.wait_for()
    assert page.locator(".ant-pagination-item-active").inner_text() == "2"
    assert reads[-1].endswith("transactions?page=2&page_size=20")
    assert not writes


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
)
@pytest.mark.parametrize(
    "scene",
    ["login", "register", "reset", "overview", "security", "apikeys", "credits"],
)
def test_account_pages_bound_long_content_and_keyboard_password_toggle(
    ui_page, width, height, scene
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    if scene in ("login", "register", "reset"):
        auth(page, load, scene, username="demo-user", email="demo@example.invalid")
        scope = page.locator(".auth-page" if scene == "reset" else ".auth-shell")
    elif scene == "credits":
        credit_fixture(page)
        load("pages/account/user_credits.html", path="/credits")
        page.get_by_role("heading", name="我的积分", exact=True).wait_for()
        scope = page.locator(".account-page")
    else:
        profile(page, load, scene)
        scope = page.locator(".account-page")
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    box = scope.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    password = scope.locator('input[type="password"]:visible').first
    if password.count():
        password = scope.locator("#" + password.get_attribute("id"))
        toggle = password.locator("..").get_by_role("button", name="显示/隐藏密码" if scene in ("login", "register") else "显示", exact=True)
        toggle = toggle.element_handle()
        toggle.focus()
        page.keyboard.press("Space")
        assert password.get_attribute("type") == "text"
        page.keyboard.press("Enter")
        assert password.get_attribute("type") == "password"
        if width <= 600:
            size = toggle.bounding_box()
            assert size["width"] >= 44 and size["height"] >= 44
    assert not errors
