"""User and redemption management contracts against built Ant Design assets."""

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from test_app_ui import ROOT, browser, ui_page  # noqa: F401


USERS = [
    dict(
        id=1,
        username="ui-test",
        email="admin@example.invalid",
        is_active=True,
        is_admin=True,
        credits_balance=200,
        created_at=1790825400,
        metrics=dict(
            projects_count=3, credits_consumed_total=9, last_active_at=1791689400
        ),
    ),
    dict(
        id=2,
        username="member",
        email="member@example.invalid",
        is_active=True,
        is_admin=False,
        credits_balance=100,
        created_at=1790825400,
        metrics=dict(
            projects_count=2, credits_consumed_total=6, last_active_at=1791689400
        ),
    ),
    dict(
        id=3,
        username="disabled",
        email=None,
        is_active=False,
        is_admin=False,
        credits_balance=0,
        created_at=1790825400,
        metrics={},
    ),
]
CODES = [
    dict(
        id=1,
        code="LAND-UNUSED",
        credits_amount=100,
        is_used=False,
        used_by=None,
        created_at=1790825400,
        expires_at=None,
    ),
    dict(
        id=2,
        code="LAND-USED",
        credits_amount=100,
        is_used=True,
        used_by=2,
        created_at=1790825400,
        expires_at=None,
    ),
]


class CreditsPageRejected(Exception):
    pass


def credits_page_context(enabled):
    """Execute the real handler without importing database/auth services.

    Existing template fixtures supply credits_enabled=True, which can hide a
    missing route context. This regression derives that context from the route.
    """
    source = ROOT / "src/landppt/web/admin_routes.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "admin_credits_page"
    )
    handler.decorator_list = []
    namespace = dict(
        Request=object,
        User=object,
        Depends=lambda dependency: None,
        get_admin_user_required=lambda: None,
        app_config=SimpleNamespace(enable_credits_system=enabled),
        HTTPException=lambda **kwargs: CreditsPageRejected(kwargs),
        templates=SimpleNamespace(
            TemplateResponse=lambda name, context: (name, context)
        ),
    )
    exec(
        compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    # Playwright's sync driver already owns the calling thread's event loop.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run, namespace["admin_credits_page"](object(), USERS[0])
        ).result()


@pytest.mark.parametrize("width", [1440, 390])
def test_enabled_credits_route_reaches_admin_ui_without_template_global(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    template, context = credits_page_context(True)
    assert template == "pages/admin/credits.html"
    reads, writes = management(
        page,
        load,
        section="credits",
        user=context["user"],
        credits_enabled=context.get("credits_enabled", False),
    )
    page.get_by_role("button", name="立即生成", exact=True).wait_for()
    assert not page.get_by_text("积分系统未启用", exact=True).count()
    assert not writes


def test_disabled_credits_route_still_rejects_before_rendering():
    with pytest.raises(CreditsPageRejected) as error:
        credits_page_context(False)
    assert error.value.args[0] == {"status_code": 404, "detail": "积分系统未启用"}


def management(page, load, section="users", **values):
    reads, writes = [], []

    def api(route):
        request = route.request
        path = urlsplit(request.url).path
        if request.method == "GET":
            reads.append(request.url)
            query = parse_qs(urlsplit(request.url).query)
            if path == "/admin/api/users":
                result = dict(
                    success=True,
                    users=USERS,
                    total=41,
                    page=int(query.get("page", [1])[0]),
                )
            elif path.startswith("/admin/api/users/"):
                result = dict(
                    success=True,
                    user={
                        **USERS[int(path.rsplit("/", 1)[1]) - 1],
                        "phone": "123456789",
                        "registration_channel": "local",
                    },
                )
            else:
                result = dict(
                    success=True,
                    codes=CODES,
                    total=41,
                    page=int(query.get("page", [1])[0]),
                )
        else:
            writes.append((request.method, path, request.post_data_json))
            result = dict(
                success=True,
                codes=[CODES[0]],
                temporary_password="temporary-fixture-password",
            )
        route.fulfill(json=result)

    page.route("**/admin/api/**", api)
    load(f"pages/admin/{section}.html", path=f"/admin/{section}", **values)
    page.get_by_role(
        "heading", name="用户管理" if section == "users" else "积分管理", exact=True
    ).wait_for()
    return reads, writes


def select(page, label, choice):
    page.get_by_role("combobox", name=label, exact=True).click()
    page.locator(".ant-select-dropdown:visible").get_by_text(choice, exact=True).click()


def test_user_create_failure_keeps_fields_and_retry_preserves_payload(ui_page):
    page, load = ui_page
    reads, unused = management(page, load)
    writes = []

    def create(route):
        if route.request.method == "GET":
            route.fallback()
            return
        writes.append(route.request.post_data_json)
        route.fulfill(
            status=500 if len(writes) == 1 else 200,
            json={"detail": "创建暂时失败"} if len(writes) == 1 else {"success": True},
        )

    page.route("**/admin/api/users", create)
    page.get_by_role("button", name="新建用户", exact=True).click()
    dialog = page.get_by_role("dialog", name="新建用户", exact=True)
    dialog.get_by_label("用户名", exact=True).fill("new-user")
    dialog.get_by_label("初始密码", exact=True).fill("fixture-password")
    dialog.get_by_label("邮箱", exact=True).fill("new@example.invalid")
    dialog.get_by_label("初始积分", exact=True).fill("25")
    dialog.get_by_role("button", name="保存用户", exact=True).click()
    dialog.get_by_text("创建暂时失败", exact=True).wait_for()
    assert (
        dialog.get_by_label("初始密码", exact=True).input_value() == "fixture-password"
    )
    dialog.get_by_role("button", name="保存用户", exact=True).click()
    dialog.wait_for(state="hidden")
    assert (
        writes
        == [
            dict(
                username="new-user",
                password="fixture-password",
                email="new@example.invalid",
                is_admin=False,
                credits_balance=25,
            )
        ]
        * 2
    )


def test_user_edit_reads_details_and_only_updates_mutable_fields(ui_page):
    page, load = ui_page
    reads, writes = management(page, load)
    page.get_by_role("button", name="编辑 member", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑用户", exact=True)
    page.wait_for_function(
        "document.querySelector('#userUsername')?.value === 'member'"
    )
    assert dialog.get_by_label("用户名", exact=True).is_disabled()
    assert dialog.get_by_label("初始密码", exact=True).count() == 0
    assert dialog.get_by_text("123456789", exact=True).is_visible()
    dialog.get_by_label("邮箱", exact=True).fill("updated@example.invalid")
    dialog.get_by_role("button", name="保存用户", exact=True).click()
    dialog.wait_for(state="hidden")
    assert writes == [
        (
            "PUT",
            "/admin/api/users/2",
            dict(email="updated@example.invalid", is_admin=False),
        )
    ]
    assert any(url.endswith("/users/2") for url in reads)


def test_user_failed_detail_read_blocks_save_and_supports_retry(ui_page):
    page, load = ui_page
    reads, writes = management(page, load)
    attempts = []

    def detail(route):
        attempts.append(route.request.url)
        if len(attempts) == 1:
            route.fulfill(status=500, json={"detail": "详情加载失败"})
        else:
            route.fallback()

    page.route("**/admin/api/users/2", detail)
    page.get_by_role("button", name="编辑 member", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑用户", exact=True)
    dialog.get_by_text("详情加载失败", exact=True).wait_for()
    assert dialog.get_by_role("button", name="保存用户", exact=True).is_disabled()
    assert not writes
    dialog.get_by_role("button", name="重试", exact=True).click()
    page.wait_for_function(
        "document.querySelector('#userUsername')?.value === 'member'"
    )
    assert not dialog.get_by_role("button", name="保存用户", exact=True).is_disabled()


def test_user_filters_sort_and_pagination_send_existing_query(ui_page):
    page, load = ui_page
    reads, writes = management(page, load)
    assert len(reads) == 1
    page.get_by_role("searchbox", name="搜索用户", exact=True).fill(" member ")
    page.get_by_role("searchbox", name="搜索用户", exact=True).press("Enter")
    select(page, "状态筛选", "活跃")
    select(page, "角色筛选", "用户")
    select(page, "排序字段", "用户名")
    page.get_by_role("button", name="降序", exact=True).click()
    page.locator(".ant-pagination-next button").click()
    page.wait_for_function(
        "document.querySelector('.ant-pagination-item-active')?.textContent === '2'"
    )
    assert parse_qs(urlsplit(reads[-1]).query) == dict(
        page_size=["20"],
        is_active=["true"],
        is_admin=["false"],
        search=["member"],
        sort_by=["username"],
        sort_dir=["asc"],
        page=["2"],
    )
    assert not writes


@pytest.mark.parametrize(
    "state,method,payload",
    [("停用 member", "DELETE", None), ("启用 disabled", "PUT", {"is_active": True})],
)
def test_user_state_changes_require_confirmation_and_keep_soft_deactivation(
    ui_page, state, method, payload
):
    page, load = ui_page
    reads, writes = management(page, load)
    page.get_by_role("button", name=state, exact=True).click()
    dialog = page.get_by_role(
        "dialog", name="停用用户" if method == "DELETE" else "启用用户", exact=True
    )
    dialog.get_by_role("button", name="取消", exact=True).click()
    assert not writes
    page.get_by_role("button", name=state, exact=True).click()
    dialog.get_by_role("button", name="确认", exact=True).click()
    dialog.wait_for(state="hidden")
    assert writes == [
        (
            method,
            "/admin/api/users/2" if method == "DELETE" else "/admin/api/users/3",
            payload,
        )
    ]


def test_user_self_controls_and_reset_password_secret(ui_page):
    page, load = ui_page
    reads, writes = management(page, load)
    assert page.get_by_role("button", name="停用 ui-test", exact=True).is_disabled()
    page.get_by_role("button", name="编辑 ui-test", exact=True).click()
    dialog = page.get_by_role("dialog", name="编辑用户", exact=True)
    page.wait_for_function(
        "document.querySelector('#userUsername')?.value === 'ui-test'"
    )
    assert dialog.get_by_role("combobox", name="角色", exact=True).is_disabled()
    dialog.get_by_role("button", name="取消", exact=True).click()
    page.get_by_role("button", name="重置密码 member", exact=True).click()
    page.get_by_role("dialog", name="重置用户密码", exact=True).get_by_role(
        "button", name="确认", exact=True
    ).click()
    secret = page.get_by_role("dialog", name="临时密码", exact=True)
    secret.get_by_text("temporary-fixture-password", exact=True).wait_for()
    secret.get_by_role("button", name="已保存", exact=True).click()
    assert writes == [("POST", "/admin/api/users/2/reset-password", None)]
    assert not page.get_by_text("temporary-fixture-password", exact=True).is_visible()


def test_credit_adjustment_validates_zero_and_keeps_failure_for_retry(ui_page):
    page, load = ui_page
    reads, unused = management(page, load)
    writes = []

    def adjust(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            status=500 if len(writes) == 1 else 200,
            json={"detail": "调整失败"} if len(writes) == 1 else {"success": True},
        )

    page.route("**/admin/api/users/2/credits", adjust)
    page.get_by_role("button", name="调整积分 member", exact=True).click()
    dialog = page.get_by_role("dialog", name="调整积分：member", exact=True)
    dialog.get_by_label("调整数量", exact=True).fill("0")
    dialog.get_by_label("调整原因", exact=True).fill("纠正重复充值")
    dialog.get_by_role("button", name="确认调整", exact=True).click()
    dialog.get_by_text("请输入非零整数", exact=True).wait_for()
    assert not writes
    dialog.get_by_label("调整数量", exact=True).fill("-5")
    dialog.get_by_role("button", name="确认调整", exact=True).click()
    dialog.get_by_text("调整失败", exact=True).wait_for()
    assert dialog.get_by_label("调整数量", exact=True).input_value() == "-5"
    dialog.get_by_role("button", name="确认调整", exact=True).click()
    dialog.wait_for(state="hidden")
    assert writes == [dict(amount=-5, description="纠正重复充值")] * 2


@pytest.mark.parametrize("optional", [True, False])
def test_code_generation_preserves_optional_payload_and_prior_results_on_failure(
    ui_page, optional
):
    page, load = ui_page
    reads, unused = management(page, load, "credits")
    assert not reads
    writes = []

    def generate(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            status=500 if len(writes) == 2 else 200,
            json=(
                {"detail": "生成失败"}
                if len(writes) == 2
                else {"success": True, "codes": [CODES[0]]}
            ),
        )

    page.route("**/admin/api/redemption-codes", generate)
    page.get_by_label("生成数量", exact=True).fill("2")
    page.get_by_label("每个兑换码积分", exact=True).fill("50")
    if optional:
        page.get_by_label("有效天数（可选）", exact=True).fill("7")
        page.get_by_label("备注（可选）", exact=True).fill("UI fixture")
    button = page.get_by_role("button", name="立即生成", exact=True)
    button.click()
    page.get_by_text("LAND-UNUSED", exact=True).wait_for()
    button.click()
    page.get_by_text("生成失败", exact=True).wait_for()
    assert page.get_by_text("LAND-UNUSED", exact=True).is_visible()
    assert page.get_by_label("生成数量", exact=True).input_value() == "2"
    expected = dict(
        count=2,
        credits_amount=50,
        **(dict(expires_in_days=7, description="UI fixture") if optional else {}),
    )
    assert writes == [expected] * 2
    page.get_by_role("button", name="复制全部", exact=True).click()
    page.get_by_text("已复制全部兑换码", exact=True).wait_for()


def test_code_list_filters_export_and_delete_only_unused(ui_page):
    page, load = ui_page
    reads, writes = management(page, load, "credits")
    page.get_by_role("tab", name="兑换码列表", exact=True).click()
    page.locator(".admin-code:visible").filter(has_text="LAND-UNUSED").wait_for()
    assert len(reads) == 1
    assert page.get_by_role("button", name="删除 LAND-USED", exact=True).count() == 0
    search = page.get_by_role("searchbox", name="搜索兑换码", exact=True)
    search.fill("LAND")
    search.press("Enter")
    page.get_by_role("spinbutton", name="创建人 ID", exact=True).fill("2")
    select(page, "兑换码状态", "未使用")
    query = dict(is_used=["false"], search=["LAND"], created_by=["2"])
    assert (
        parse_qs(
            urlsplit(
                page.get_by_role("link", name="导出 CSV", exact=True).get_attribute(
                    "href"
                )
            ).query
        )
        == query
    )
    page.get_by_role("button", name="删除 LAND-UNUSED", exact=True).click()
    dialog = page.get_by_role("dialog", name="删除兑换码", exact=True)
    dialog.get_by_role("button", name="确认", exact=True).click()
    dialog.wait_for(state="hidden")
    assert writes == [("DELETE", "/admin/api/redemption-codes/1", None)]
    assert parse_qs(urlsplit(reads[-1]).query) == dict(
        page_size=["20"], page=["1"], **query
    )


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
)
@pytest.mark.parametrize("section", ["users", "credits"])
def test_management_layout_and_actions_fit_viewport(ui_page, width, height, section):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    reads, writes = management(page, load, section)
    if section == "users":
        trigger = page.get_by_role("button", name="新建用户", exact=True)
        trigger.click()
        dialog = page.get_by_role("dialog", name="新建用户", exact=True)
        box = dialog.locator(".ant-modal-container").bounding_box()
        assert 0 <= box["y"] and box["y"] + box["height"] <= height + 1
        for _ in range(8):
            page.keyboard.press("Tab")
            assert page.evaluate("!!document.activeElement.closest('.ant-modal-wrap')")
        page.keyboard.press("Escape")
        dialog.wait_for(state="hidden")
        assert trigger.evaluate("e => e === document.activeElement")
    else:
        page.get_by_role("tab", name="兑换码列表", exact=True).click()
        page.locator(".admin-code:visible").filter(has_text="LAND-UNUSED").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert not errors
    assert not writes


@pytest.mark.parametrize("section", ["users", "credits"])
def test_management_non_admin_does_not_fetch_data(ui_page, section):
    page, load = ui_page
    reads = []
    page.route(
        "**/admin/api/**",
        lambda route: (reads.append(route.request.url), route.fulfill(json={})),
    )
    load(
        f"pages/admin/{section}.html",
        user=dict(id=2, username="member", is_admin=False),
    )
    page.get_by_text("需要管理员权限", exact=True).wait_for()
    assert not reads


def test_disabled_credits_hides_user_controls_and_blocks_code_reads(ui_page):
    page, load = ui_page
    reads, writes = management(page, load, credits_enabled=False)
    assert page.get_by_role("button", name="调整积分 member", exact=True).count() == 0
    assert (
        page.get_by_role("navigation", name="管理后台", exact=True)
        .get_by_role("link", name="积分", exact=True)
        .count()
        == 0
    )
    page.get_by_role("button", name="新建用户", exact=True).click()
    dialog = page.get_by_role("dialog", name="新建用户", exact=True)
    assert dialog.get_by_label("初始积分", exact=True).count() == 0
    dialog.get_by_label("用户名", exact=True).fill("new")
    dialog.get_by_label("初始密码", exact=True).fill("fixture")
    dialog.get_by_role("button", name="保存用户", exact=True).click()
    dialog.wait_for(state="hidden")
    assert "credits_balance" not in writes[-1][2]
    reads.clear()
    load("pages/admin/credits.html", credits_enabled=False)
    page.get_by_text("积分系统未启用", exact=True).wait_for()
    assert not reads
