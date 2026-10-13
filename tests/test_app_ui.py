"""Browser regressions for navigation, bounded profile layout and modal focus.

Render actual frontend files with fixture GET responses; no app/database or AI.
"""

import ast
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/landppt/web/static"


def template_environment(directory):
    """Use the real presentation filter without starting database/AI services."""
    source = ROOT / "src/landppt/web/route_modules/support.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    formatter = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_strftime_filter"
    )
    namespace = {"datetime": datetime, "Any": Any}
    exec(
        compile(ast.Module(body=[formatter], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    env = Environment(loader=FileSystemLoader(directory), autoescape=True)
    env.filters["strftime"] = namespace["_strftime_filter"]
    return env


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:
            instance = runtime.chromium.launch()
        except Exception as exc:
            pytest.skip(f"Chromium is not available: {exc}")
        yield instance
        instance.close()


@pytest.fixture
def ui_page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.set_default_timeout(5000)
    env = template_environment(ROOT / "src/landppt/web/templates")
    user = dict(
        id=1,
        username="ui-test",
        is_admin=True,
        is_active=True,
        email="long-email-" * 20 + "@example.invalid",
        created_at="2026-10-02",
    )
    project = dict(
        project_id="ui-test",
        title="示例项目",
        topic="布局与键盘测试",
        scenario="general",
        status="completed",
        todo_board=None,
        updated_at=datetime(2026, 10, 2).timestamp(),
        project_metadata={},
        outline={"slides": [{"title": "封面", "content": []}]},
        slides_data=[
            dict(
                slide_id="slide-1",
                slide_number=1,
                title="封面",
                render_mode="html",
                html_content='<html><body style="margin:0;width:1280px;height:720px;background:#17263e">Original slide</body></html>',
            )
        ],
    )
    state = {"html": ""}

    def forward(route):
        path = unquote(urlsplit(route.request.url).path)
        if "bootstrap@5.1.3/dist/css/bootstrap.min.css" in route.request.url:
            # Keep the CDN reset and utility precedence in the isolated editor
            # fixture; these declarations also apply in the live browser.
            route.fulfill(
                body="*,::before,::after{box-sizing:border-box}.d-flex{display:flex!important}.align-items-center{align-items:center!important}",
                content_type="text/css",
            )
        elif route.request.url.startswith("https:"):
            route.abort()
        elif path.startswith("/static/"):
            source = STATIC / path.removeprefix("/static/")
            if source.is_file() and source.resolve().is_relative_to(STATIC.resolve()):
                mime = (
                    mimetypes.guess_type(str(source))[0] or "application/octet-stream"
                )
                route.fulfill(body=source.read_bytes(), content_type=mime)
            else:
                route.fulfill(status=404, body="")
        elif route.request.resource_type == "document":
            route.fulfill(body=state["html"], content_type="text/html")
        else:
            assert route.request.method == "GET", route.request.url
            route.fulfill(
                body=json.dumps(
                    {
                        "success": True,
                        "enabled": False,
                        "data": [],
                        "config": {},
                        "notifications": [],
                        "unread_count": 0,
                        "templates": [],
                        "packages": [],
                        "images": [],
                        "tags": [],
                        "users": [],
                        "total": 0,
                        "page": 1,
                        "total_pages": 1,
                        "pagination": {
                            "current_page": 1,
                            "total_pages": 1,
                            "total_count": 0,
                        },
                    }
                ),
                content_type="application/json",
            )

    context.route("**/*", forward)

    def load(template, path="/projects", **overrides):
        values = dict(
            user=user,
            request=SimpleNamespace(state=SimpleNamespace(user=user)),
            credits_enabled=True,
            project=project,
            projects=[project],
            recent_projects=[project],
            total=1,
            page=1,
            page_size=20,
            status_filter=None,
            current_provider="openai",
            current_config={},
            available_providers=[],
            provider_status={},
            registration_enabled=True,
            active_tab="login",
            scenarios=[],
            unattended_defaults=None,
            template_options=[],
            narration_video_tools_enabled=False,
        )
        values.update(overrides)
        values["request"] = SimpleNamespace(state=SimpleNamespace(user=values["user"]))
        state["html"] = env.get_template(template).render(**values)
        page.goto("http://ui.test" + path, wait_until="networkidle")
        return page

    yield page, load
    context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (320, 568), (844, 390)])
@pytest.mark.parametrize("role", ["guest", "user", "admin"])
def test_mobile_menu_keeps_all_role_links_reachable(ui_page, width, height, role):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    user = None if role == "guest" else dict(username="test", is_admin=role == "admin")
    load("pages/project/projects_list.html", user=user)
    assert page.locator("#appMain").bounding_box()["y"] < 140
    toggle = page.get_by_role("button", name="菜单", exact=True)
    toggle.click()
    drawer = page.get_by_role("dialog", name="导航", exact=True)
    assert toggle.get_attribute("aria-expanded") == "true"
    assert drawer.locator('a[href="/admin"]').count() == (role == "admin")
    assert drawer.locator('a[href="/auth/login?tab=register"]').count() == (
        role == "guest"
    )
    for link in drawer.locator("nav a").all():
        link.scroll_into_view_if_needed()
        box = link.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert box["height"] >= 44
        assert link.evaluate(
            "e => {const r=e.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !!hit && e.contains(hit)}"
        )
    assert drawer.locator('a[href="/projects"]').get_attribute("aria-current") == "page"
    page.keyboard.press("Escape")
    assert not drawer.is_visible()
    assert toggle.evaluate("e => e === document.activeElement")


@pytest.mark.parametrize("width", [390, 320])
def test_profile_tabs_and_long_email_stay_inside_mobile_panel(ui_page, width):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load("pages/account/profile.html", path="/auth/profile")
    for selector in (".profile-shell", ".profile-tabs", ".profile-info-list"):
        box = page.locator(selector).bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert page.locator(".profile-info-list").evaluate(
        "e => e.scrollWidth <= e.clientWidth + 1"
    )
    page.get_by_role("tab", name="基本信息").focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    assert (
        page.get_by_role("tab", name="我的积分").get_attribute("aria-selected")
        == "true"
    )


@pytest.mark.parametrize(
    "width,height",
    [(1440, 900), (1024, 768), (720, 450), (601, 768), (390, 844), (320, 568)],
)
def test_dashboard_summary_keeps_projects_near_top_without_overflow(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load(
        "pages/project/project_dashboard.html",
        path="/dashboard",
        total_projects=999999,
        completed_projects=999999,
        in_progress_projects=0,
        draft_projects=0,
        recent_projects=[
            dict(
                project_id="ui-test",
                title="长项目名称与研发团队的跨部门协作计划" * 4,
                scenario="general",
                status="completed",
                updated_at=datetime(2026, 10, 2).timestamp(),
            )
        ],
    )
    header = page.locator(".dashboard-header").bounding_box()
    recent = page.locator(".recent-projects-header").bounding_box()
    assert recent["y"] - header["y"] <= (260 if width <= 600 else 140)
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for card in page.locator(".stat-card").all():
        assert card.evaluate(
            "e => {const card=e.getBoundingClientRect();"
            "return [...e.querySelectorAll('.stat-icon,.stat-number,.stat-title')]"
            ".every(child=>{const r=child.getBoundingClientRect();"
            "return r.left>=card.left && r.right<=card.right && "
            "child.scrollWidth<=child.clientWidth+1})}"
        )
    create = page.get_by_role("link", name="创建项目", exact=True).first
    all_projects = page.get_by_role("link", name="所有项目", exact=True)
    assert create.get_attribute("href") == "/scenarios"
    assert all_projects.get_attribute("href") == "/projects"
    for action in (create, all_projects):
        assert action.bounding_box()["height"] >= (44 if width <= 600 else 32)
        assert action.evaluate(
            "e => {const r=e.getBoundingClientRect();"
            "return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
        )


@pytest.fixture
def detail_project():
    return dict(
        project_id="ui-detail",
        title="项目工作区体验优化与下一阶段计划",
        topic="产品体验、协作流程与交付质量",
        scenario="general",
        status="completed",
        version=3,
        requirements="优先呈现关键进度和可执行操作。",
        created_at=datetime(2026, 10, 2).timestamp(),
        slides_html="<html><body>Original slide</body></html>",
        outline=dict(
            title="产品体验与交付计划",
            slides=[
                dict(
                    title="项目目标与具体实施步骤" * 3,
                    page_number=i + 1,
                    content_points=["明确核心目标。", "跟踪结果并及时调整。"],
                )
                for i in range(3)
            ],
        ),
    )


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (1024, 768), (390, 844), (320, 568)]
)
@pytest.mark.parametrize("status", ["completed", "in_progress"])
def test_project_detail_compact_layout_keeps_stage_and_outline_actions_reachable(
    ui_page, detail_project, width, height, status
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    project = {**detail_project, "status": status}
    board = dict(
        overall_progress=100 if status == "completed" else 69,
        stages=[
            dict(
                id=stage_id,
                name=name,
                description="阶段说明与协作要求" * 3,
                status="running" if status == "in_progress" and i == 4 else "completed",
                progress=45,
            )
            for i, (stage_id, name) in enumerate(
                [
                    ("requirements_confirmation", "需求确认"),
                    ("research", "资料研究"),
                    ("outline_generation", "大纲生成"),
                    ("template_selection", "模板选择"),
                    ("ppt_creation", "PPT 生成"),
                ]
            )
        ],
    )
    load(
        "pages/project/project_detail.html",
        path="/projects/ui-detail",
        project=project,
        todo_board=board,
        versions=[],
    )
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    hero = page.locator(".project-detail-hero").bounding_box()
    outline = page.locator(".outline-panel").bounding_box()
    if status == "completed" and width >= 980:
        assert outline["y"] - hero["y"] <= 550
    elif status == "completed":
        assert outline["y"] - hero["y"] <= 780
    else:
        for description in page.locator(".stage-description").all():
            assert description.is_visible()
            assert description.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    disclosure = page.locator(".detail-stage-list").get_by_role(
        "button", name=re.compile("阶段状态")
    )
    assert (
        disclosure.get_attribute("aria-expanded")
        == str(status == "in_progress").lower()
    )
    disclosure.focus()
    page.keyboard.press("Enter")
    assert (
        disclosure.get_attribute("aria-expanded") == str(status == "completed").lower()
    )
    page.keyboard.press("Enter")
    assert (
        disclosure.get_attribute("aria-expanded")
        == str(status == "in_progress").lower()
    )
    assert page.get_by_role("link", name="预览 PPT").is_visible() == (
        status == "completed"
    )
    assert page.get_by_role("link", name="查看 TODO 看板").is_visible() == (
        status == "in_progress"
    )
    page.get_by_role("button", name="第 1 页更多操作", exact=True).click()
    assert page.get_by_role("menuitem", name="上移", exact=True).get_attribute("aria-disabled") == "true"
    page.keyboard.press("Escape")
    page.get_by_role("button", name="第 3 页更多操作", exact=True).click()
    assert page.get_by_role("menuitem", name="下移", exact=True).get_attribute("aria-disabled") == "true"
    page.keyboard.press("Escape")
    if width <= 600:
        surface = page.locator(".outline-surface").bounding_box()
        for card in page.locator("#compactView .outline-slide-card").all():
            box = card.bounding_box()
            assert box["x"] >= surface["x"]
            assert box["x"] + box["width"] <= surface["x"] + surface["width"]
        for button in page.locator("#compactView .outline-slide-actions button").all():
            box = button.bounding_box()
            assert box["width"] >= 44 and box["height"] >= 44
            assert button.evaluate(
                "e => {const r=e.getBoundingClientRect();"
                "const card=e.closest('.outline-slide-card').getBoundingClientRect();"
                "return r.left>=card.left && r.right<=card.right}"
            )
    page.get_by_role("button", name="切换为详细视图").click()
    assert page.locator("#detailView").is_visible()
    assert not page.locator("#compactView").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    page.get_by_role("button", name="切换为简洁视图").click()
    assert page.locator("#compactView").is_visible()
    page.locator("#compactView [aria-label='查看详情']").first.click()
    dialog = page.get_by_role("dialog", name="第 1 页详情")
    dialog.wait_for(state="visible")
    dialog.get_by_role("button", name="关闭", exact=True).last.click()
    assert not dialog.is_visible()


@pytest.mark.parametrize("width", [1440, 320])
@pytest.mark.parametrize(
    "outline", [None, {"content": "旧格式大纲内容。" + "LONG_" * 50}]
)
def test_project_detail_draft_and_legacy_content_remain_bounded(
    ui_page, detail_project, width, outline
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load(
        "pages/project/project_detail.html",
        path="/projects/ui-detail",
        project={**detail_project, "status": "draft", "outline": outline},
        todo_board=None,
        versions=[
            dict(
                version=2,
                description="版本说明与修订记录" * 12,
                timestamp=datetime(2026, 10, 2),
            )
        ],
    )
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert page.locator(".detail-stage-list").count() == 0
    assert page.get_by_role("button", name="恢复此版本").is_visible()
    if outline:
        assert page.locator(".detail-legacy-content").inner_text() == outline["content"]
    else:
        assert page.locator(".outline-panel").count() == 0


@pytest.mark.parametrize("template", ["projects_list", "project_dashboard"])
def test_project_dialog_traps_focus_and_restores_trigger(ui_page, template):
    page, load = ui_page
    load(f"pages/project/{template}.html")
    trigger = page.get_by_role("button", name="重命名").first
    trigger.click()
    dialog = page.get_by_role("dialog", name="重命名项目")
    dialog.wait_for()
    field = dialog.get_by_role("textbox", name="项目名称")
    field.fill("")
    dialog.get_by_role("button", name="保存", exact=True).click()
    page.get_by_text("项目名称不能为空", exact=True).wait_for()
    for key in ("Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab"):
        page.keyboard.press(key)
        assert page.evaluate("!!document.activeElement.closest('.ant-modal-wrap')")
    page.keyboard.press("Escape")
    assert not dialog.is_visible()
    assert trigger.evaluate("e => e === document.activeElement")


def test_config_tabs_support_keyboard_selection(ui_page):
    page, load = ui_page
    load("pages/settings/ai_config.html", path="/ai-config")
    tabs = page.get_by_role("tablist")
    tabs.get_by_role("tab", name="AI 提供者", exact=True).focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    selected = tabs.get_by_role("tab", name=re.compile("生成参数$"))
    assert selected.get_attribute("aria-selected") == "true"
    assert selected.evaluate("e => e === document.activeElement")
    assert page.locator("#generation-params").is_visible()
    tabs.get_by_role("tab", name="AI 提供者", exact=True).click()
    assert (
        tabs.get_by_role("tab", name="AI 提供者", exact=True).get_attribute(
            "aria-selected"
        )
        == "true"
    )


def test_shared_confirm_can_open_above_project_dialog(ui_page):
    page, load = ui_page
    load("pages/project/projects_list.html")
    page.get_by_role("button", name="重命名").first.click()
    page.wait_for_timeout(70)
    page.evaluate("() => { window.confirmResult = Notify.confirm('示例确认'); }")
    page.locator(".ln-dialog-overlay").wait_for()
    for _ in range(4):
        page.keyboard.press("Tab")
        assert page.evaluate("!!document.activeElement.closest('.ln-dialog-overlay')")
    page.locator(".ln-dialog-overlay").get_by_role("button", name="取消").click()
    assert page.evaluate("!!document.activeElement.closest('.ant-modal-wrap')")


@pytest.mark.parametrize("width,height", [(390, 844), (844, 390)])
@pytest.mark.parametrize(
    "template,path,trigger,modal",
    [
        (
            "pages/template/global_master_templates.html",
            "/global-master-templates",
            "#createTemplateBtn",
            ".ant-modal",
        ),
        (
            "pages/image/image_gallery.html",
            "/image-gallery",
            "#upload-trigger",
            ".ant-modal",
        ),
        (
            "pages/admin/users.html",
            "/admin",
            "#createUserBtn",
            ".ant-modal",
        ),
    ],
)
def test_existing_modal_can_close_and_reopen_with_focus_restored(
    ui_page, width, height, template, path, trigger, modal
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load(template, path=path)
    button = page.locator(trigger)
    original_overflow = page.evaluate("document.body.style.overflow")
    for _ in range(2):
        button.click()
        dialog = page.locator(modal)
        dialog.wait_for()
        page.wait_for_function(
            "selector => document.querySelector(selector).getAttribute('aria-modal') === 'true'",
            arg=modal,
        )
        for _ in range(8):
            page.keyboard.press("Tab")
            assert page.evaluate(
                "selector => !!document.activeElement.closest(selector)", modal
            )
        content = dialog.locator(".ant-modal-container").bounding_box()
        assert content["y"] >= 0 and content["y"] + content["height"] <= height + 1
        page.keyboard.press("Escape")
        dialog.wait_for(state="hidden")
        page.wait_for_function(
            "selector => document.activeElement.matches(selector)", arg=trigger
        )
        assert page.evaluate("document.body.style.overflow") == original_overflow


def test_long_template_card_fits_mobile_without_changing_preview_document(ui_page):
    page, load = ui_page
    page.set_viewport_size({"width": 320, "height": 568})
    template = dict(
        id=999,
        template_name="Template-" * 12,
        description="长模板描述与布局检查。" * 10,
        tags=["商务", "学术"],
        user_id=1,
        usage_count=3,
        created_by="test",
        html_template='<html><body style="margin:0;width:1280px;height:720px;background:#17263e"><h1>Original preview</h1></body></html>',
    )

    def respond(route):
        assert route.request.method == "GET"
        path = urlsplit(route.request.url).path
        data = (
            dict(
                templates=[template],
                pagination=dict(current_page=1, total_pages=1, total_count=1),
            )
            if path.endswith("/global-master-templates/")
            else template if path.endswith("/999") else {}
        )
        route.fulfill(body=json.dumps(data), content_type="application/json")

    page.route("**/api/global-master-templates/**", respond)
    load("pages/template/global_master_templates.html", path="/global-master-templates")
    card = page.locator(".template-card")
    card.wait_for()
    assert card.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert card.locator("button:visible").count() == 3
    for button in card.locator("button:visible").all():
        box = button.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 320
    summary = card.get_by_role("button", name=template["template_name"] + "更多操作")
    summary.click()
    assert page.get_by_role("menuitem").count() == 5
    page.get_by_role("menuitem", name="复制", exact=True).focus()
    page.keyboard.press("Escape")
    page.get_by_role("menu").wait_for(state="hidden")
    assert summary.evaluate("e => e === document.activeElement")
    card.get_by_role("button", name="编辑", exact=True).click()
    page.locator(".template-editor-modal").wait_for()
    page.keyboard.press("Escape")
    frame = page.frame_locator(".template-preview-iframe")
    assert (
        frame.get_by_role("heading", name="Original preview").inner_text()
        == "Original preview"
    )
    assert frame.locator("body").evaluate("e => getComputedStyle(e).width") == "1280px"
    assert (
        frame.locator("body").evaluate("e => getComputedStyle(e).backgroundColor")
        == "rgb(23, 38, 62)"
    )


@pytest.mark.parametrize("width,height", [(390, 844), (320, 568), (844, 390)])
def test_admin_menu_keeps_navigation_and_keyboard_exit_reachable(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load("pages/admin/users.html", path="/admin/users")
    nav = page.get_by_role("navigation", name="管理后台", exact=True)
    assert nav.is_visible()
    for link in nav.locator("a").all():
        box = link.bounding_box()
        assert 0 <= box["x"] <= width - box["width"]
        assert box["height"] >= 44
    assert nav.locator('[aria-current="page"]').get_attribute("href") == "/admin/users"
    toggle = page.get_by_role("button", name="菜单", exact=True)
    toggle.click()
    drawer = page.get_by_role("dialog", name="导航", exact=True)
    drawer.get_by_role("link", name="管理后台", exact=True).wait_for()
    page.keyboard.press("Escape")
    assert not drawer.is_visible()
    assert nav.is_visible()
    assert toggle.evaluate("e => e === document.activeElement")


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize(
    "template,path,field,button",
    [
        (
            "pages/project/projects_list.html",
            "/projects",
            "#renameProjectTitle",
            ".ant-modal button.ant-btn-primary",
        ),
        (
            "pages/settings/ai_config.html",
            "/ai-config",
            'input[name="openai_api_key"]',
            "button.ant-btn-primary:visible",
        ),
        (
            "pages/admin/users.html",
            "/admin/users",
            "#userUsername",
            ".ant-modal button.ant-btn-primary",
        ),
        (
            "pages/auth/login.html",
            "/auth/login",
            "#username",
            "#loginFormElement button[type=submit]",
        ),
    ],
)
def test_primary_controls_share_scale_across_app_shells(
    ui_page, width, template, path, field, button
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load(template, path=path)
    if path == "/projects":
        page.get_by_role("button", name="重命名").first.click()
    elif path == "/ai-config":
        page.locator("#field-openai_api_key").wait_for()
    elif path == "/admin/users":
        page.get_by_role("button", name="新建用户", exact=True).click()
    control = page.locator(field)
    assert control.is_visible()
    assert control.evaluate("e => getComputedStyle(e).fontSize") == (
        "16px" if width < 600 else "14px"
    )
    visible_control = (
        control.locator("..") if path in ("/auth/login", "/ai-config") else control
    )
    assert visible_control.bounding_box()["height"] >= (44 if width < 600 else 32)
    assert visible_control.bounding_box()["height"] <= (46 if width < 600 else 42)
    primary = page.locator(button).first
    assert primary.evaluate("e => getComputedStyle(e).fontSize") == "14px"
    assert primary.evaluate("e => getComputedStyle(e).borderRadius") == "8px"
    assert (
        primary.evaluate("e => getComputedStyle(e).backgroundColor")
        == "rgb(17, 17, 17)"
    )
    colors = primary.evaluate(
        "e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor]"
    )

    def luminance(value):
        channels = [int(c) / 255 for c in value[4:-1].split(",")]
        linear = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return sum(c * w for c, w in zip(linear, [0.2126, 0.7152, 0.0722]))

    light, dark = sorted([luminance(color) for color in colors], reverse=True)
    assert (light + 0.05) / (dark + 0.05) >= 4.5


@pytest.mark.parametrize("width,height", [(390, 844), (320, 568)])
def test_mobile_auth_has_brand_and_single_input_boundary(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load("pages/auth/login.html", path="/auth/login")
    assert page.locator(".app-brand").is_visible()
    assert page.locator(".brand-panel").count() == 0
    assert (
        page.locator("#username").evaluate("e => getComputedStyle(e).borderTopWidth")
        == "1px"
    )
    panel = page.locator(".form-shell").bounding_box()
    assert panel["x"] >= 0 and panel["x"] + panel["width"] <= width
    toggle = page.locator("#loginFormElement").get_by_role(
        "button", name="显示", exact=True
    )
    box = toggle.bounding_box()
    assert box["width"] >= 44 and box["height"] >= 44
    assert toggle.evaluate(
        "e => {const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
    )
    toggle.click()
    assert page.locator("#password").get_attribute("type") == "text"


@pytest.mark.parametrize("width,height", [(390, 844), (320, 568), (844, 390)])
@pytest.mark.parametrize("auto_repair", [False, True])
def test_ai_sidebar_header_and_long_input_keep_actions_visible(
    ui_page, width, height, auto_repair
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load(
        "pages/project/project_slides_editor.html",
        path="/projects/ui-test/edit",
        enable_auto_layout_repair=auto_repair,
    )
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    dialog = page.get_by_role("dialog", name=re.compile("^AI 编辑助手"))
    field = dialog.get_by_role("textbox", name="AI 编辑指令", exact=True)
    field.fill("修改当前页的标题并调整正文间距。" * 80)
    page.wait_for_timeout(450)
    for controls in (
        dialog.locator(".ant-drawer-header"),
        dialog.locator(".ant-drawer-header button"),
        field,
        dialog.get_by_role("button", name="发送", exact=True),
    ):
        for control in controls.all():
            box = control.bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
            assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
    assert dialog.get_by_role("button", name="发送", exact=True).evaluate(
        "e => {const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
    )
    send_box = dialog.get_by_role("button", name="发送", exact=True).bounding_box()
    for name in ["上传图片", "视觉模式", "自由对话", "清除上下文"]:
        button = dialog.get_by_role("button", name=name, exact=True)
        box = button.bounding_box()
        assert abs(box["y"] - send_box["y"]) < 2
        assert box["height"] >= (44 if width <= 600 else 32)
    assert dialog.locator(".ant-drawer-header button").count() == (
        4 if auto_repair else 3
    )
    for button in dialog.locator(".ant-drawer-header button").all():
        assert button.evaluate(
            "e => {const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
        )
    page.keyboard.press("Escape")
    assert not page.locator("#aiEditSidebar").evaluate(
        "e=>e.classList.contains('open')"
    )


@pytest.mark.parametrize("width", [1440, 390, 320])
@pytest.mark.parametrize(
    "tab",
    ["ai-providers", "generation-params", "jev-config", "app-config", "image-service"],
)
def test_every_settings_tab_keeps_form_fields_inside_page(ui_page, width, tab):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load("pages/settings/ai_config.html", path="/ai-config")
    labels = {
        "ai-providers": "AI 提供者",
        "generation-params": "生成参数",
        "jev-config": "决策模型配置",
        "app-config": "应用配置",
        "image-service": "图片服务",
    }
    page.get_by_role("tab", name=labels[tab], exact=True).click()
    panel = page.locator("#" + tab)
    if tab == "ai-providers":
        for provider in ["LandPPT", "Anthropic Claude", "Google Gemini"]:
            panel.locator(".ant-collapse-header").filter(has_text=provider).click()
        panel.locator(".ant-collapse-header").filter(has_text="模型任务配置").click()
    elif tab == "image-service":
        for name in [
            "enable_image_service",
            "enable_local_images",
            "enable_network_search",
            "enable_ai_generation",
        ]:
            panel.locator("#field-" + name).click()
    elif tab == "app-config":
        control = panel.locator("#field-reload")
        initial = control.get_attribute("aria-checked")
        control.focus()
        page.keyboard.press("Space")
        assert control.get_attribute("aria-checked") != initial
        page.keyboard.press("Space")
        assert control.get_attribute("aria-checked") == initial
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    visible = 0
    for field in panel.locator("input,textarea,button[role=switch]").all():
        if not field.is_visible():
            continue
        visible += 1
        box = field.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert visible > 0


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
def test_generation_save_stays_clickable_while_editing_last_section(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load("pages/settings/ai_config.html", path="/ai-config")
    page.get_by_role("tab", name="生成参数", exact=True).click()
    page.locator("#generation-params .ant-card").last.scroll_into_view_if_needed()
    assert (
        page.locator("#generation-params .settings-savebar").bounding_box()["height"]
        < 100
    )
    save = page.get_by_role("button", name="保存生成参数", exact=True)
    box = save.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert save.evaluate(
        "e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
    )


def test_generation_slider_and_number_still_synchronize(ui_page):
    page, load = ui_page
    load("pages/settings/ai_config.html", path="/ai-config")
    page.get_by_role("tab", name="生成参数", exact=True).click()
    page.locator("#field-temperature").fill("1.3")
    slider = page.get_by_role("slider", name="温度 TEMPERATURE滑块")
    if not slider.count():
        slider = page.get_by_role("slider").nth(1)
    assert slider.get_attribute("aria-valuenow") == "1.3"
    slider.focus()
    page.keyboard.press("ArrowRight")
    assert page.locator("#field-temperature").input_value() == "1.4"


@pytest.mark.parametrize("width", [1440, 320])
@pytest.mark.parametrize(
    "provider,name",
    [
        ("openai", "openai_use_responses_api"),
        ("openai", "openai_enable_reasoning"),
        ("anthropic", "anthropic_enable_reasoning"),
    ],
)
def test_provider_switches_share_size_and_keep_keyboard_linkage(
    ui_page, width, provider, name
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load("pages/settings/ai_config.html", path="/ai-config")
    if provider == "anthropic":
        page.locator(".ant-collapse-header").filter(has_text="Anthropic Claude").click()
    field = page.locator("#field-" + name)
    assert field.bounding_box()["width"] >= 44
    initial = field.get_attribute("aria-checked")
    field.focus()
    page.keyboard.press("Space")
    assert field.get_attribute("aria-checked") != initial
    if name.endswith("enable_reasoning"):
        effort = page.locator("#field-" + provider + "_reasoning_effort")
        assert effort.is_disabled() == (field.get_attribute("aria-checked") != "true")
    page.keyboard.press("Space")
    assert field.get_attribute("aria-checked") == initial


@pytest.mark.parametrize("width", [390, 320])
def test_image_source_keyboard_toggle_and_json_field_remain_usable(ui_page, width):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load("pages/settings/ai_config.html", path="/ai-config")
    page.get_by_role("tab", name="图片服务", exact=True).click()
    page.locator("#field-enable_image_service").click()
    for name, dependent in [
        ("enable_local_images", "max_local_images_per_slide"),
        ("enable_network_search", "max_network_images_per_slide"),
        ("enable_ai_generation", "max_ai_images_per_slide"),
    ]:
        control = page.locator("#field-" + name)
        control.click()
        assert page.locator("#field-" + dependent).is_visible()
        control.focus()
        page.keyboard.press("Space")
        assert page.locator("#field-" + dependent).count() == 0
        page.keyboard.press("Space")
        assert page.locator("#field-" + dependent).is_visible()
    resolution = page.locator('textarea[name="ai_image_resolution_presets"]')
    resolution.fill(json.dumps({"openai_image": ["1536x1024"] * 80}))
    box = resolution.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert page.evaluate("document.documentElement.scrollWidth") <= width


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
def test_admin_settings_tabs_and_long_form_save_are_accessible(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    load("pages/admin/community.html", path="/admin/community")
    page.locator(".system-config-block").last.scroll_into_view_if_needed()
    save = page.locator("#saveSystemDefaultsBtn")
    box = save.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert save.evaluate(
        "e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
    )
    tab = page.get_by_role("tab", name="系统默认配置", exact=True)
    tab.focus()
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.locator(".community-sponsors").wait_for()
    last = page.get_by_role("tab", name=re.compile("赞助感谢页$"))
    assert last.get_attribute("aria-selected") == "true"
    assert last.evaluate("e=>e===document.activeElement")
    page.keyboard.press("Home")
    page.keyboard.press("Enter")
    assert page.locator(".community-system").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= width


@pytest.mark.parametrize("width", [1440, 320])
@pytest.mark.parametrize("provider", ["smtp", "resend"])
def test_mail_settings_provider_and_secret_toggle_keep_values(ui_page, width, provider):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load("pages/admin/smtp.html", path="/admin/smtp")
    page.locator(f'input[name="email_provider"][value="{provider}"]').check()
    assert page.locator(f"#{provider}ConfigSection").is_visible()
    other = "smtp" if provider == "resend" else "resend"
    assert not page.locator(f"#{other}ConfigSection").is_visible()
    field = page.locator(
        "#resend_api_key" if provider == "resend" else "#smtp_password"
    )
    field.fill("fixture-secret")
    button = (
        field.locator("..")
        .get_by_role("button", name="显示", exact=True)
        .element_handle()
    )
    assert button.get_attribute("aria-label")
    button.click()
    assert field.get_attribute("type") == "text"
    assert button.get_attribute("aria-pressed") == "true"
    assert field.input_value() == "fixture-secret"
    button.click()
    assert field.get_attribute("type") == "password"
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert page.get_by_role("button", name="保存邮件设置").count() == 1


@pytest.mark.parametrize("width", [1440, 320])
def test_oauth_switches_keep_keyboard_and_visible_track(ui_page, width):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    load("pages/admin/oauth.html", path="/admin/oauth")
    for provider in ["github", "linuxdo"]:
        field = page.locator(f"#{provider}_enabled")
        was_checked = field.get_attribute("aria-checked")
        field.focus()
        page.keyboard.press("Space")
        assert field.get_attribute("aria-checked") != was_checked
        box = field.bounding_box()
        assert box["width"] >= 44 and box["height"] >= 22
        assert box["x"] >= 0 and box["x"] + box["width"] <= width


@pytest.mark.parametrize(
    "tab,category,field,value,button",
    [
        (
            "generation-params",
            "generation_params",
            "temperature",
            "1.2",
            "保存生成参数",
        ),
        (
            "app-config",
            "app_config",
            "base_url",
            "https://ui.example.invalid",
            "保存应用配置",
        ),
        (
            "image-service",
            "image_service",
            "openai_image_model",
            "fixture-model",
            "保存配置",
        ),
        (
            "ai-providers",
            "model_roles",
            "outline_model_name",
            "fixture-outline",
            "保存模型任务配置",
        ),
    ],
)
def test_settings_layout_keeps_original_save_payload(
    ui_page, tab, category, field, value, button
):
    page, load = ui_page
    requests = []

    def capture(route):
        if route.request.method == "POST":
            requests.append(route.request.post_data_json)
        route.fulfill(
            body='{"success":true,"config":{}}', content_type="application/json"
        )

    page.route("**/api/config/" + category, capture)
    load("pages/settings/ai_config.html", path="/ai-config")
    labels = {
        "generation-params": "生成参数",
        "app-config": "应用配置",
        "image-service": "图片服务",
        "ai-providers": "AI 提供者",
    }
    page.get_by_role("tab", name=labels[tab], exact=True).click()
    if category == "model_roles":
        page.locator(".ant-collapse-header").filter(has_text="模型任务配置").click()
    if category == "image_service":
        page.locator(".image-credentials-collapse .ant-collapse-header").filter(
            has_text="OpenAI 图片生成"
        ).click()
    page.locator(f'input[name="{field}"]').fill(value)
    page.get_by_role("button", name=button, exact=True).click()
    page.wait_for_timeout(100)
    assert len(requests) == 1
    assert requests[0]["config"][field] == value


@pytest.mark.parametrize("width,height", [(1440, 900), (320, 568)])
def test_settings_test_result_dialog_fits_and_restores_focus(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    page.route(
        "**/api/ai/providers/test",
        lambda route: route.fulfill(json={"success": True, "message": "隔离测试结果"}),
    )
    load("pages/settings/ai_config.html", path="/ai-config")
    trigger = page.get_by_role("button", name="测试连接", exact=True).first
    trigger.click()
    dialog = page.get_by_role("dialog").filter(has_text="连接测试")
    dialog.wait_for()
    assert dialog.get_attribute("aria-modal") == "true"
    close = dialog.get_by_role("button", name="关闭测试结果")
    box = close.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    assert trigger.evaluate("e=>e===document.activeElement")


def test_settings_admin_fields_remain_hidden_for_regular_user(ui_page):
    page, load = ui_page
    load(
        "pages/settings/ai_config.html",
        path="/ai-config",
        user=dict(username="reader", is_admin=False),
    )
    assert page.get_by_role("tab", name="应用配置", exact=True).count() == 0
    assert page.locator('input[name="apryse_license_key"]').count() == 0
    assert page.locator('select[name="unattended_default_stop_stage"]').count() == 0


@pytest.mark.parametrize("width", [1440, 320])
@pytest.mark.parametrize("kind", ["success", "error"])
def test_settings_notifications_share_component_and_bound_long_messages(
    ui_page, width, kind
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    message = "隔离回归提示：https://" + "service-endpoint-" * 12 + ".invalid"
    page.route(
        "**/api/config/generation_params",
        lambda route: route.fulfill(
            status=503 if kind == "error" else 200,
            json={"detail": message} if kind == "error" else {"success": True},
        ),
    )
    load("pages/settings/ai_config.html", path="/ai-config")
    page.get_by_role("tab", name="生成参数", exact=True).click()
    page.get_by_role("button", name="保存生成参数", exact=True).click()
    notice = (
        page.get_by_role("alert").filter(has_text=message)
        if kind == "error"
        else page.get_by_text("配置已保存，已实时生效", exact=True)
    )
    notice.wait_for()
    box = notice.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert page.evaluate("document.documentElement.scrollWidth") <= width


@pytest.fixture
def gallery_page(ui_page):
    page, load = ui_page
    images = [
        dict(
            image_id=f"gallery-{index}",
            title="AI Generated: Abstract network connections 演示素材标题" * 4,
            filename=f"network-{index}.png",
            source_type="ai_generated",
            file_size=35840,
            description="示例素材说明",
            tags="network, abstract",
            category="ai_generated",
            width=400,
            height=300,
            format="png",
            created_at=1790870400,
            access_count=1,
        )
        for index in range(3)
    ]
    requests = []

    def forward(route):
        requests.append((route.request.method, route.request.url))
        assert route.request.method == "GET"
        path = urlsplit(route.request.url).path
        if "/thumbnail/" in path or "/view/" in path:
            route.fulfill(
                body='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect width="400" height="300" fill="#12354b"/></svg>',
                content_type="image/svg+xml",
            )
        elif "/detail/" in path:
            route.fulfill(
                body=json.dumps({"success": True, "image": images[0]}),
                content_type="application/json",
            )
        else:
            route.fulfill(
                body=json.dumps(
                    {
                        "success": True,
                        "images": images,
                        "pagination": {
                            "current_page": 1,
                            "total_pages": 1,
                            "total_count": 3,
                        },
                    }
                ),
                content_type="application/json",
            )

    page.route("**/api/image/**", forward)
    load("pages/image/image_gallery.html", path="/image-gallery")
    page.locator(".image-card").first.wait_for()
    return page, images, requests


@pytest.mark.parametrize("width", [1440, 1024, 768, 390, 320, 844])
def test_gallery_long_titles_and_card_actions_fit_their_cards(gallery_page, width):
    page, images, _ = gallery_page
    page.set_viewport_size({"width": width, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for card in page.locator(".image-card").all():
        box = card.bounding_box()
        title = card.locator(".image-card-body h2")
        assert title.inner_text() == images[0]["title"]
        assert title.bounding_box()["height"] <= 42
        for button in card.locator(".image-card-actions button").all():
            bounds = button.bounding_box()
            assert bounds["x"] >= box["x"]
            assert bounds["x"] + bounds["width"] <= box["x"] + box["width"]
            assert bounds["height"] >= (44 if width <= 600 else 32)
        assert card.get_by_role("button", name="复制链接").is_visible()
        assert card.get_by_role("button", name="下载", exact=True).is_visible()
        assert card.get_by_role(
            "button", name="删除 " + images[0]["title"], exact=True
        ).is_visible()


@pytest.mark.parametrize("width", [1440, 320])
@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_gallery_thumbnail_opens_detail_with_keyboard(gallery_page, width, key):
    page, images, requests = gallery_page
    page.set_viewport_size({"width": width, "height": 844})
    thumbnail = page.locator(".image-card-preview").first
    thumbnail.focus()
    page.keyboard.press(key)
    page.get_by_role("dialog", name="图片详情", exact=True).wait_for(state="visible")
    assert (
        page.get_by_role("dialog")
        .get_by_text(images[0]["title"], exact=True)
        .is_visible()
    )
    assert any(url.endswith("/detail/gallery-0") for _, url in requests)
    page.keyboard.press("Escape")
    assert not page.get_by_role("dialog", name="图片详情", exact=True).is_visible()
    assert thumbnail.evaluate("e=>e===document.activeElement")


@pytest.mark.parametrize("width", [1440, 320])
def test_gallery_batch_selection_keeps_state_and_clears_on_exit(gallery_page, width):
    page, _, _ = gallery_page
    page.set_viewport_size({"width": width, "height": 844})
    trigger = page.get_by_role("button", name="批量选择", exact=True)
    trigger.click()
    assert trigger.get_attribute("aria-pressed") == "true"
    assert page.locator(".image-batch-toolbar").is_visible()
    page.locator(".image-card-check input").first.check()
    assert page.get_by_text("已选择 1 张", exact=True).is_visible()
    assert page.locator(".image-card-selected").count() == 1
    trigger.click()
    assert trigger.get_attribute("aria-pressed") == "false"
    assert page.locator(".image-card-check input").count() == 0
    assert page.locator(".image-card-selected").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth") <= width


def test_gallery_delete_still_requires_confirmation_and_cancel_does_not_write(
    gallery_page,
):
    page, images, requests = gallery_page
    page.get_by_role(
        "button", name="删除 " + images[0]["title"], exact=True
    ).first.click()
    dialog = page.get_by_role("dialog", name="删除图片", exact=True)
    dialog.wait_for(state="visible")
    dialog.get_by_role("button", name="取消").click()
    assert page.locator(".image-card").count() == 3
    assert all(method == "GET" for method, _ in requests)


@pytest.fixture
def generator_page(ui_page):
    page, load = ui_page
    # The isolated UI fixture blocks CDN JavaScript. This suite exercises native
    # details and fullscreen controls, so only stub the unused wizard's Modal.
    # The screenshot audit separately loads the real Bootstrap bundle and CSS.
    page.add_init_script("window.bootstrap = {Modal: class {show() {} hide() {}}};")
    page.route(
        "**/bootstrap@5.1.3/dist/css/bootstrap.min.css",
        lambda route: route.fulfill(
            body="*,::before,::after{box-sizing:border-box}"
            ".d-flex{display:flex!important}.align-items-center{align-items:center!important}"
            ".modal{display:none;position:fixed;inset:0}",
            content_type="text/css",
        ),
    )
    requests = []
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    original = '<html><body style="margin:0;width:1280px;height:720px;background:#eee7d4">Original presentation</body></html>'
    titles = ["研发设计工具与核心工作流程" * 8, "核心操作", "下一阶段计划"]
    run_state = {"run": None}

    def status(route):
        requests.append(route.request.method)
        route.fulfill(body=json.dumps(run_state), content_type="application/json")

    page.route("**/unattended/status", status)

    def open_workspace(task_status="completed"):
        run_state["run"] = (
            None
            if task_status == "idle"
            else dict(
                task_status=task_status,
                status=task_status,
                topic="研发与设计协作" * 12,
                overall_progress=42 if task_status == "running" else 100,
                stages=[
                    dict(
                        id="outline",
                        name="生成大纲",
                        status="completed",
                        message="内容已保存",
                    ),
                    dict(
                        id="ppt",
                        name="生成幻灯片",
                        status=task_status,
                        message="正在生成第2页",
                        error="设计服务暂时不可用" if task_status == "failed" else None,
                    ),
                ],
                error="设计服务暂时不可用" if task_status == "failed" else None,
                download_url=(
                    "/downloads/example.mp4" if task_status == "completed" else None
                ),
            )
        )
        project = dict(
            project_id="ui-generator",
            title="生成工作区长项目名称" * 8,
            topic="研发与设计协作",
            status="draft" if task_status == "idle" else "completed",
            project_metadata={},
            outline=dict(slides=[dict(title=title) for title in titles]),
            slides_data=(
                []
                if task_status == "idle"
                else [
                    dict(
                        page_number=i + 1,
                        title=title,
                        render_mode="html",
                        html_content=original,
                    )
                    for i, title in enumerate(titles)
                ]
            ),
        )
        load(
            "pages/project/todo_board_with_editor.html",
            path="/projects/ui-generator/todo-editor",
            project=project,
            todo_board=dict(task_id=project["project_id"], title=project["title"]),
            unattended_active=task_status == "running",
        )
        page.wait_for_timeout(650)

    return page, open_workspace, run_state, original, titles, requests, errors


@pytest.mark.parametrize(
    "width,height",
    [
        (1910, 915),
        (1440, 900),
        (1024, 768),
        (720, 450),
        (390, 844),
        (320, 568),
        (844, 390),
    ],
)
def test_generator_completed_workspace_fits_and_preserves_preview_content(
    generator_page, width, height
):
    page, open_workspace, _, original, titles, requests, errors = generator_page
    page.set_viewport_size(dict(width=width, height=height))
    open_workspace()
    assert not errors
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert (
        page.locator("#generatorStatusUI .ant-badge-status-text").inner_text()
        == "生成完成"
    )
    assert (
        page.get_by_role("button", name=re.compile("阶段详情")).get_attribute(
            "aria-expanded"
        )
        == "false"
    )
    assert not page.locator("#generationProgress").is_visible()
    assert page.locator("#unattendedMonitor").evaluate(
        "e => e.scrollHeight <= e.clientHeight + 1"
    )
    assert page.locator("#unattendedMonitor").bounding_box()["height"] < (
        200 if width <= 600 else 140
    )
    if width > 600 and height > 600:
        assert page.evaluate("document.documentElement.scrollHeight") <= height
        box = page.locator(".slide-preview").first.bounding_box()
        assert box["y"] + box["height"] < height
    else:
        assert (
            page.locator("#slidesContainer").evaluate(
                "e => getComputedStyle(e).overflowY"
            )
            == "visible"
        )
    headers = [
        header.bounding_box()["height"]
        for header in page.locator(".slide-header").all()
    ]
    assert max(headers) == min(headers)
    for index, frame in enumerate(page.locator(".slide-preview iframe").all()):
        preview = frame.locator("..").bounding_box()
        box = frame.bounding_box()
        assert abs(box["width"] - preview["width"]) < 1.5
        assert abs(box["height"] - preview["height"]) < 1.5
        assert frame.get_attribute("srcdoc") == original
        title = page.locator(".slide-title").nth(index)
        assert title.inner_text() == title.get_attribute("title") == titles[index]
    for button in page.locator(".fullscreen-btn").all():
        box = button.bounding_box()
        assert box["height"] >= (44 if width <= 600 else 36)
        assert button.evaluate("e => e.getBoundingClientRect().right <= innerWidth")
    page.locator(".fullscreen-btn").first.click()
    assert page.locator("#fullscreenIframe").get_attribute("srcdoc") == original
    page.keyboard.press("Escape")
    assert not page.locator("#fullscreenOverlay").is_visible()
    assert requests and all(method == "GET" for method in requests)


@pytest.mark.parametrize("task_status", ["completed", "running", "failed", "idle"])
def test_generator_monitor_keeps_status_errors_and_details_reachable(
    generator_page, task_status
):
    page, open_workspace, run_state, _, _, requests, errors = generator_page
    page.set_viewport_size(dict(width=390, height=844))
    open_workspace(task_status)
    assert not errors
    if task_status == "idle":
        assert not page.locator("#unattendedMonitor").is_visible()
        assert page.get_by_role("button", name="开始生成", exact=True).is_visible()
        return
    details = page.get_by_role("button", name=re.compile("阶段详情"))
    assert (details.get_attribute("aria-expanded") == "true") == (
        task_status == "failed"
    )
    if task_status == "failed":
        assert page.locator(".unattended-ant-error").first.is_visible()
        details.click()
        assert page.locator(".unattended-ant-error").first.is_visible()
    elif task_status == "running":
        assert page.get_by_role("button", name="停止无人值守任务").is_visible()
        assert "正在生成幻灯片" in page.locator(".unattended-ant-topic").inner_text()
    details.focus()
    page.keyboard.press("Enter")
    assert details.get_attribute("aria-expanded") == "true"
    # The actual controller polls the same run, preserving Ant disclosure/focus.
    page.wait_for_timeout(5100)
    assert details.get_attribute("aria-expanded") == "true"
    assert details.evaluate("e => e === document.activeElement")
    page.keyboard.press("Enter")
    assert details.get_attribute("aria-expanded") == "false"
    assert all(method == "GET" for method in requests)


def test_generator_resizing_keeps_frame_inside_actual_card_width(generator_page):
    page, open_workspace, _, original, _, _, errors = generator_page
    open_workspace()
    for width, height in [(1024, 768), (390, 844), (844, 390), (1440, 900)]:
        page.set_viewport_size(dict(width=width, height=height))
        page.wait_for_timeout(80)
        for frame in page.locator(".slide-preview iframe").all():
            preview = frame.locator("..").bounding_box()
            box = frame.bounding_box()
            assert abs(preview["width"] - box["width"]) < 1.5
            assert abs(preview["height"] - box["height"]) < 1.5
            assert frame.get_attribute("srcdoc") == original
    assert not errors
