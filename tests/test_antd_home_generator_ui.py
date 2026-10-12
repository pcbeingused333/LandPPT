"""Actual Ant home/workspace controls with isolated APIs and generation events."""

import json
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, generator_page, ui_page  # noqa: F401

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
ORIGINAL = '<html><body style="margin:0;width:1280px;height:720px;background:#eee7d4">Original presentation</body></html>'
TITLE = "研发设计流程与生成工作区"


def slide(number=1):
    return dict(
        page_number=number,
        title=f"第 {number} 页",
        render_mode="html",
        html_content=ORIGINAL,
    )


def setup_workspace(
    page, load, mode="package", active=False, completed=False, auto=False, outline_titles=None, unattended_run=None
):
    page.add_init_script("window.bootstrap = {Modal: class {show() {} hide() {}}};")
    page.add_init_script(
        """window.testStreams = []; window.testOpened = [];
        window.open = (url) => { testOpened.push(url); };
        window.EventSource = class {
            static OPEN = 1; static CONNECTING = 0; static CLOSED = 2;
            constructor(url) { this.url = url; this.readyState = 1; testStreams.push(this);
                queueMicrotask(() => this.onopen?.({})); }
            close() { this.readyState = 2; }
        };
        window.sendGenerationEvent = data => testStreams.at(-1).onmessage({data: JSON.stringify(data)});
    """
    )
    state = dict(reads=[], writes=[], fail=False, selected=True)

    def api(route):
        req = route.request
        path = urlsplit(req.url).path
        (state["reads"] if req.method == "GET" else state["writes"]).append(
            (path, req.method)
        )
        result = dict(project_metadata=dict(template_mode=mode, generation_mode=mode))
        if path.endswith("unattended/status"):
            result = dict(run=unattended_run)
        elif path.endswith("selected-global-template"):
            result = dict(
                template=dict(template_name="研究报告", created_by="user"),
                is_user_selected=state["selected"],
            )
        route.fulfill(status=503 if state["fail"] else 200, json=result)

    page.route("**/api/projects/**", api)
    project = dict(
        project_id="ui-generator",
        title=TITLE,
        topic="研发",
        status="completed" if completed else "draft",
        project_metadata=dict(template_mode=mode, generation_mode=mode),
        outline=dict(slides=[dict(title=title) for title in (["封面", "内容"] if outline_titles is None else outline_titles)]),
        slides_data=[slide(1), slide(2)] if completed else [],
    )
    load(
        "pages/project/todo_board_with_editor.html",
        path="/projects/ui-generator/todo-editor"
        + ("?auto_start=true" if auto else ""),
        project=project,
        todo_board=dict(task_id="ui-generator", title=TITLE),
        unattended_active=active,
    )
    page.get_by_role("heading", name=TITLE, exact=True).wait_for()
    return state


def start(page):
    page.get_by_role("button", name="开始生成", exact=True).click()
    expect(page.get_by_role("button", name="暂停", exact=True)).to_be_visible()
    expect(page.locator("#generatorStatusUI .ant-badge-status-text")).to_have_text(
        "正在生成"
    )


def send(page, **event):
    page.evaluate("data => sendGenerationEvent(data)", event)


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize(
    "scene", ["home", "home-long-provider", "idle", "completed", "error"]
)
def test_home_workspace_geometry_and_primary_actions(ui_page, width, height, scene):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    if scene.startswith("home"):
        load(
            "pages/home/index.html",
            path="/home",
            ai_provider="openai" if scene == "home" else "unrecognised-provider-" * 30,
        )
        page.get_by_role("heading", name="创建你的演示文稿").wait_for()
        action = page.get_by_role("link", name="开始创建 PPT", exact=True)
        expect(action).to_have_attribute("href", "/create")
    else:
        setup_workspace(page, load, completed=scene == "completed")
        if scene == "error":
            start(page)
            send(page, type="error", message="设计生成失败，已保留内容。")
            expect(page.get_by_role("alert")).to_have_text("设计生成失败，已保留内容。")
            for label in ["暂停", "继续", "停止生成"]:
                assert page.get_by_role("button", name=label, exact=True).count() == 0
            action = page.get_by_role("button", name="重新开始", exact=True)
        else:
            action = page.get_by_role(
                "button",
                name="打开编辑器" if scene == "completed" else "开始生成",
                exact=True,
            )
        assert not page.locator("#generatorControlState").is_visible()
        if scene == "completed":
            assert page.locator("#generatorStatusUI .ant-progress").count() == 0
            for frame in page.locator(".slide-preview iframe").all():
                assert frame.get_attribute("srcdoc") == ORIGINAL
                box, preview = frame.bounding_box(), frame.locator("..").bounding_box()
                assert abs(box["width"] - preview["width"]) < 1.5
                assert abs(box["height"] - preview["height"]) < 1.5
    expect(action).to_be_visible()
    box = action.bounding_box()
    assert box["y"] + box["height"] <= height
    assert box["height"] >= (44 if width <= 600 else 32)
    assert action.evaluate(
        "e => {const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors


@pytest.mark.parametrize(
    "provider,label",
    [
        ("landppt", "LandPPT"),
        ("anthropic", "Anthropic Claude"),
        ("google", "Google Gemini"),
        ("gemini", "Google Gemini"),
        ("ollama", "Ollama"),
        ("local-custom", "local-custom"),
    ],
)
def test_home_provider_and_navigation_are_existing_links(ui_page, provider, label):
    page, load = ui_page
    load("pages/home/index.html", path="/home", ai_provider=provider)
    expect(page.locator(".home-provider .ant-tag")).to_have_text(label)
    assert page.get_by_role("list", name="创建流程").locator("li").count() == 3
    for name, path in [("打开工作台", "/dashboard"), ("系统配置", "/ai-config")]:
        expect(page.get_by_role("link", name=name, exact=True)).to_have_attribute(
            "href", path
        )
    assert [
        item.get_attribute("href") for item in page.locator(".home-shortcut").all()
    ] == ["/projects", "/global-master-templates", "/image-gallery"]


def test_home_missing_provider_and_public_json_escape(ui_page):
    page, load = ui_page
    load("pages/home/index.html", path="/home", ai_provider=None)
    page.get_by_role("heading", name="创建你的演示文稿").wait_for()
    assert page.locator(".home-provider").count() == 0
    load(
        "pages/home/index.html",
        path="/home",
        ai_provider="</script><script>window.injection=true</script>",
    )
    expect(page.locator(".home-provider .ant-tag")).to_have_text(
        "</script><script>window.injection=true</script>"
    )
    assert page.evaluate("window.injection") is None


def test_generation_double_start_pause_resume_and_progress(ui_page):
    page, load = ui_page
    state = setup_workspace(page, load)
    page.get_by_role("button", name="开始生成", exact=True).evaluate(
        "e => {e.click();e.click();}"
    )
    expect(page.get_by_role("button", name="暂停", exact=True)).to_be_visible()
    assert page.evaluate("testStreams.length") == 1
    send(page, type="progress", total=4, completed=1, message="设计第二页")
    expect(page.locator("#generatorStatusUI [role=status]")).to_contain_text("1/4")
    expect(page.locator("#generatorStatusUI [role=progressbar]")).to_have_attribute(
        "aria-valuenow", "25"
    )
    page.get_by_role("button", name="暂停", exact=True).click()
    expect(page.get_by_role("button", name="继续", exact=True)).to_be_visible()
    assert page.evaluate("testStreams[0].readyState") == 2
    assert state["writes"] == [("/api/projects/ui-generator/slides/cancel", "POST")]
    page.get_by_role("button", name="继续", exact=True).click()
    expect(page.get_by_role("button", name="暂停", exact=True)).to_be_visible()
    page.wait_for_function("testStreams.length === 2")
    assert state["writes"][-1] == (
        "/api/projects/ui-generator/slides/clear-cancel",
        "POST",
    )
    send(page, type="slide", slide_data=slide(1), total=4)
    expect(page.get_by_role("button", name="打开编辑器", exact=True)).to_be_visible()
    assert page.locator(".slide-preview iframe").get_attribute("srcdoc") == ORIGINAL


def test_stop_confirmation_cancel_keyboard_focus_and_request(ui_page):
    page, load = ui_page
    state = setup_workspace(page, load)
    start(page)
    stop = page.get_by_role("button", name="停止生成", exact=True)
    stop.click()
    dialog = page.get_by_role("dialog", name="操作确认")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="取消").focus()
    page.keyboard.press("Tab")
    assert dialog.evaluate("e => e.contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(stop).to_be_focused()
    assert not state["writes"]
    stop.click()
    dialog.get_by_role("button", name="确认", exact=True).click()
    expect(page.get_by_role("button", name="继续生成", exact=True)).to_be_visible()
    assert state["writes"] == [("/api/projects/ui-generator/slides/cancel", "POST")]
    assert page.evaluate("testStreams[0].readyState") == 2


@pytest.mark.parametrize("partial", [False, True])
def test_terminal_event_closes_stream_and_exposes_only_valid_actions(ui_page, partial):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1), total=2)
    send(
        page,
        type="complete",
        total=2,
        succeeded=1 if partial else 2,
        partial=partial,
        message="部分页面待重新生成" if partial else "所有页面已完成",
    )
    expect(page.get_by_role("button", name="打开编辑器", exact=True)).to_be_visible()
    assert page.get_by_role("button", name="暂停", exact=True).count() == 0
    assert page.get_by_role("button", name="停止生成", exact=True).count() == 0
    assert page.evaluate("testStreams[0].readyState") == 2
    if partial:
        expect(
            page.get_by_role("button", name="补生成失败页", exact=True)
        ).to_be_enabled()
        expect(page.locator("#generatorStatusUI [role=progressbar]")).to_have_attribute(
            "aria-valuenow", "50"
        )
    else:
        assert page.locator("#generatorStatusUI .ant-progress").count() == 0
        assert page.locator("#ui-startBtn").count() == 0
    page.get_by_role("button", name="打开编辑器", exact=True).click()
    page.get_by_role("button", name="幻灯片放映", exact=True).click()
    assert page.evaluate("testOpened") == [
        "/projects/ui-generator/edit",
        "/projects/ui-generator/fullscreen",
    ]


def test_unattended_workspace_never_exposes_manual_controls_or_auto_starts(ui_page):
    page, load = ui_page
    state = setup_workspace(page, load, active=True, auto=True)
    page.wait_for_timeout(650)
    assert page.evaluate("testStreams.length") == 0
    assert page.locator(".generator-ant-actions button").count() == 0
    expect(page.locator(".welcome-message-title")).to_have_text("任务正在运行")
    expect(page.locator(".welcome-message-subtitle")).not_to_contain_text("开始生成")
    assert not state["writes"]


def test_auto_start_uses_one_existing_stream(ui_page):
    page, load = ui_page
    setup_workspace(page, load, auto=True)
    expect(page.get_by_role("button", name="暂停", exact=True)).to_be_visible()
    assert page.evaluate("testStreams.length") == 1


@pytest.mark.parametrize("mode", ["package", "global"])
def test_settings_menu_links_and_escape_restore_focus(ui_page, mode):
    page, load = ui_page
    setup_workspace(page, load, mode=mode)
    trigger = page.get_by_role("button", name="生成设置", exact=True)
    trigger.click()
    menu = page.get_by_role("menu")
    expect(menu).to_be_visible()
    expect(
        menu.get_by_role(
            "link", name="切换到自由设计" if mode == "package" else "切换到快速模式"
        )
    ).to_have_attribute(
        "href",
        "/projects/ui-generator/template-selection?mode="
        + ("freeform" if mode == "package" else "package"),
    )
    expect(menu.get_by_role("link", name="决策模型配置")).to_have_attribute(
        "href", "/ai-config#jev-config"
    )
    menu.get_by_role("menuitem").first.focus()
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
    expect(trigger).to_be_focused()


def test_missing_template_confirmation_cancellation_keeps_start_action(ui_page):
    page, load = ui_page
    state = setup_workspace(page, load, mode="global")
    state["selected"] = False
    page.get_by_role("button", name="开始生成", exact=True).click()
    dialog = page.get_by_role("dialog", name="操作确认")
    expect(dialog).to_contain_text("需要先选择模板")
    dialog.get_by_role("button", name="取消").click()
    expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    assert page.evaluate("testStreams.length") == 0
    assert not state["writes"]


def test_workspace_adapter_has_only_explicit_public_data(ui_page):
    page, load = ui_page
    setup_workspace(page, load)
    data = json.loads(page.locator("#antdData").text_content())
    assert data == dict(
        page="generator-workspace",
        projectId="ui-generator",
        title=TITLE,
        generationMode="package",
        unattendedActive=False,
        slideTitles=["封面", "内容"],
    )
    assert page.locator("#generatorControlState").get_attribute("aria-hidden") == "true"
