"""Shared dark chrome and the merged workspace, using real built resources."""

import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import HTML, open_scene, setup


def workspace(page, load, view="slides", empty=False):
    def merged(template, **kwargs):
        project = kwargs["project"]
        project.update(version=1, created_at="2026-10-23", confirmed_requirements={"topic": "研发协作"}, slides_html=None)
        board = SimpleNamespace(task_id=project["project_id"], title=project["title"], overall_progress=100, stages=[])
        return load(template, **kwargs, workspace_view=view, todo_board=board, versions=[])

    return setup(page, merged, empty=empty)


@pytest.mark.parametrize("width,height", [(1920, 1080), (1440, 900), (1280, 800), (1024, 768), (1000, 768), (390, 844), (320, 568)])
def test_workspace_panels_and_original_continuous_previews(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    state = workspace(page, load)
    expect(page.get_by_role("region", name="连续幻灯片预览")).to_be_visible()
    expect(page.locator(".continuous-preview iframe")).to_have_count(2)
    assert page.locator(".continuous-preview iframe").first.get_attribute("srcdoc") == HTML
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    rect = page.locator(".continuous-preview").bounding_box()
    assert rect["height"] > 50 and rect["y"] + rect["height"] <= height + 1
    if width >= 1024:
        for selector in (".workspace-assistant", ".workspace-files-host", ".workspace-preview-host"):
            assert page.locator(selector).bounding_box()["width"] >= 210
        rail = page.locator("#slidesSidebar").bounding_box()
        host = page.locator(".workspace-files-host").bounding_box()
        assert rail["width"] <= host["width"] + 1
        for tab in page.locator(".editor-document-tabs .ant-segmented-item-label").all():
            box = tab.bounding_box()
            assert box["x"] >= rail["x"] and box["x"] + box["width"] <= rail["x"] + rail["width"] + 1
            assert tab.evaluate("node => node.scrollWidth <= node.clientWidth + 1")
    page.screenshot(path=f"artifacts/ui-redesign/workspace-{width}.png", full_page=True)
    assert not state["errors"] and not state["writes"]


def test_workspace_switches_in_place_and_preserves_editor_document(ui_page):
    page, load = ui_page
    state = workspace(page, load)
    original = page.locator("#slideFrame").get_attribute("srcdoc")
    page.evaluate("window.workspaceSentinel = 42")
    tabs = page.get_by_label("项目工作区视图")
    tabs.get_by_text("概览", exact=True).click()
    expect(page.get_by_text("项目信息", exact=True)).to_be_visible()
    tabs.get_by_text("大纲", exact=True).click()
    expect(page.locator(".todo-ant-page")).to_be_visible()
    tabs.get_by_text("生成", exact=True).click()
    expect(page.locator(".generator-ant-workspace")).to_be_visible()
    tabs.get_by_text("编辑", exact=True).click()
    expect(page.get_by_role("region", name="连续幻灯片预览")).to_be_visible()
    page.get_by_role("button", name="编辑第 2 页").click()
    expect(page.locator("#slideFrame")).to_be_visible()
    assert page.evaluate("window.workspaceSentinel") == 42
    assert page.locator("#slideFrame").get_attribute("srcdoc") == original
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("view", ["overview", "planning", "generate"])
@pytest.mark.parametrize("entry", ["route", "query"])
def test_nonediting_views_release_the_assistant_panel_on_initial_load(ui_page, view, entry):
    page, load = ui_page

    def with_query(template, **kwargs):
        if entry == "query":
            kwargs["path"] += f"?workspace={view}"
        return load(template, **kwargs)

    state = workspace(page, with_query, view=view if entry == "route" else "slides")
    expect(page.locator(".main-editor")).to_have_attribute("data-workspace-view", view)
    expect(page.get_by_role("region", name="AI 编辑助手", exact=True)).not_to_be_visible()
    expect(page.locator(".workspace-assistant-panel")).not_to_be_visible()
    expect(page.locator(".ant-splitter-bar:has(+ .workspace-assistant-panel)")).not_to_be_visible()
    preview = page.locator(".workspace-preview-host").bounding_box()
    splitter = page.locator(".project-splitter").bounding_box()
    assert preview["x"] + preview["width"] >= splitter["x"] + splitter["width"] - 1
    if entry == "route":
        page.screenshot(path=f"artifacts/ui-redesign/assistant-scope-{view}.png", full_page=True)
    page.get_by_label("项目工作区视图").get_by_text("编辑", exact=True).click()
    expect(page.get_by_role("region", name="AI 编辑助手", exact=True)).to_be_visible()
    assert not state["errors"] and not state["writes"]


def test_assistant_defaults_open_on_editor_entry_and_keeps_the_chat_draft(ui_page):
    page, load = ui_page
    state = workspace(page, load)
    assistant = page.get_by_role("region", name="AI 编辑助手", exact=True)
    expect(assistant).to_be_visible()
    command = page.get_by_role("textbox", name="AI 编辑指令", exact=True)
    command.fill("切换页面后继续编辑这个草稿")
    tabs = page.get_by_label("项目工作区视图")
    for label in ("概览", "大纲", "生成"):
        page.get_by_role("button", name="收起 AI 助手", exact=True).click()
        expect(assistant).not_to_be_visible()
        tabs.get_by_text(label, exact=True).click()
        expect(page.locator(".workspace-assistant-panel")).not_to_be_visible()
        tabs.get_by_text("编辑", exact=True).click()
        expect(assistant).to_be_visible()
        expect(command).to_have_value("切换页面后继续编辑这个草稿")
    tabs.get_by_text("概览", exact=True).click()
    expect(assistant).not_to_be_visible()
    tabs.get_by_text("编辑", exact=True).click()
    expect(assistant).to_be_visible()
    expect(command).to_have_value("切换页面后继续编辑这个草稿")
    assert not state["errors"] and not state["writes"]


def test_mobile_assistant_closes_when_leaving_editing_and_retains_the_draft(ui_page):
    page, load = ui_page
    page.set_viewport_size({"width": 390, "height": 844})
    state = workspace(page, load, view="overview")
    assistant = page.get_by_role("dialog", name=re.compile("^AI 编辑助手"))
    expect(assistant).not_to_be_visible()
    tabs = page.get_by_label("项目工作区视图")
    tabs.get_by_text("编辑", exact=True).click()
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(assistant).to_be_visible()
    page.get_by_role("textbox", name="AI 编辑指令", exact=True).fill("手机端的编辑草稿")
    # App navigation may come from an assistant action while its modal covers the tabs.
    page.evaluate("document.dispatchEvent(new CustomEvent('landppt:navigate', {detail: '/projects/ui-editor/todo?view=planning', cancelable: true}))")
    expect(page.locator(".main-editor")).to_have_attribute("data-workspace-view", "planning")
    expect(assistant).not_to_be_visible()
    tabs.get_by_text("编辑", exact=True).click()
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(page.get_by_role("textbox", name="AI 编辑指令", exact=True)).to_have_value("手机端的编辑草稿")
    assert not state["errors"] and not state["writes"]


def test_sidebar_persists_and_search_submits_the_existing_query(ui_page):
    page, load = ui_page
    workspace(page, load)
    page.get_by_role("button", name="收起导航", exact=True).click()
    expect(page.locator(".app-sidebar")).to_have_css("width", "64px")
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("button", name="展开导航", exact=True)).to_be_visible()
    page.get_by_role("button", name="展开导航", exact=True).click()
    search = page.locator(".app-sidebar").get_by_role("textbox", name="搜索项目", exact=True)
    search.fill("研发计划")
    search.press("Enter")
    expect(page).to_have_url(re.compile(r"/projects\?search="))


def test_splitter_drag_and_collapse_keep_native_artwork_and_drafts(ui_page):
    page, load = ui_page
    state = workspace(page, load)
    assistant = page.locator(".workspace-assistant")
    before = assistant.bounding_box()["width"]
    # The assistant is the right-hand rail, so its splitter bar is the last one and widens leftwards.
    bar = page.locator(".project-splitter > .ant-splitter-bar [role=separator]").last.bounding_box()
    x, y = bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 4
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 20, y, steps=4)
    page.mouse.up()
    page.wait_for_function("previous => document.querySelector('.workspace-assistant').getBoundingClientRect().width > previous + 5", arg=before)
    command = page.get_by_role("textbox", name="AI 编辑指令", exact=True)
    command.fill("保留这段编辑要求")
    page.get_by_role("button", name="收起 AI 助手", exact=True).click()
    expect(assistant).not_to_be_visible()
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(command).to_have_value("保留这段编辑要求")
    page.get_by_role("button", name="展开或收起幻灯片列表").click()
    expect(page.locator("#slidesSidebar")).not_to_be_visible()
    page.get_by_role("button", name="展开或收起幻灯片列表").click()
    expect(page.locator("#slidesSidebar")).to_be_visible()
    assert page.locator("#slideFrame").get_attribute("srcdoc") == HTML
    assert not state["errors"] and not state["writes"]


def test_primary_button_and_secondary_text_have_readable_dark_contrast(ui_page):
    page, load = ui_page
    workspace(page, load)
    colors = page.evaluate("""() => {
      const tokens = getComputedStyle(document.documentElement);
      return Object.fromEntries(['surface','text','secondary','muted','primary','on-primary'].map(key => [key,tokens.getPropertyValue('--lp-'+key).trim()]));
    }""")

    def luminance(hex_color):
        values = [int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in values]
        return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))

    for foreground in ("text", "secondary", "muted"):
        assert (luminance(colors[foreground]) + .05) / (luminance(colors["surface"]) + .05) >= 4.5
    assert (luminance(colors["primary"]) + .05) / (luminance(colors["on-primary"]) + .05) >= 4.5


def test_project_file_folders_open_in_place_with_an_explicit_project_scope(ui_page):
    page, load = ui_page
    state = workspace(page, load)
    reads = []

    def library(route):
        reads.append(route.request.url)
        route.fulfill(json={"projects": [], "files": [], "project": {"id": "ui-editor", "title": "研发协作"}, "pagination": {"current_page": 1, "total_count": 0}})

    page.route("**/api/source-library?*", library)
    page.route("**/api/artifact-library?*", library)
    page.evaluate("window.workspaceSentinel = 42")
    page.locator(".workspace-file-folders").get_by_role("link", name="来源资料").click()
    expect(page.locator(".source-library")).to_be_visible()
    page.locator(".workspace-file-folders").get_by_role("link", name="导出文件").click()
    expect(page.locator(".artifact-library")).to_be_visible()
    assert reads and all(parse_qs(urlsplit(url).query)["project_id"] == ["ui-editor"] for url in reads)
    assert page.evaluate("window.workspaceSentinel") == 42
    assert not state["errors"] and not state["writes"]


def test_source_updates_reach_the_retained_planning_view(ui_page):
    page, load = ui_page
    state = workspace(page, load)
    tabs = page.get_by_label("项目工作区视图")
    tabs.get_by_text("大纲", exact=True).click()
    expect(page.locator(".todo-ant-page")).to_be_visible()
    tabs.get_by_text("编辑", exact=True).click()
    page.evaluate("window.dispatchEvent(new CustomEvent('landppt:project-sources-saved', {detail: {projectId: 'ui-editor', summary: {files: ['最新资料.pdf'], urls: []}}}))")
    tabs.get_by_text("大纲", exact=True).click()
    expect(page.get_by_text("资料已更新，请重新生成大纲以应用修改。现有页面不会自动更新。", exact=True)).to_be_visible()
    assert not state["errors"] and not state["writes"]


def test_empty_workspace_shows_a_planning_action_without_an_editable_canvas(ui_page):
    page, load = ui_page
    state = workspace(page, load, empty=True)
    expect(page.get_by_role("region", name="AI 编辑助手", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="确认内容需求", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="一键配图", exact=True)).to_be_disabled()
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("width", [390, 844])
def test_mobile_files_and_ai_drawers_remain_reachable(ui_page, width):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    workspace(page, load)
    page.get_by_role("button", name="展开或收起幻灯片列表").click()
    expect(page.locator("#slidesSidebar")).to_be_visible()
    search = page.get_by_role("textbox", name="搜索项目文件")
    search.fill("实施")
    expect(page.locator(".slide-thumbnail:visible")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.locator("#slidesSidebar")).not_to_be_visible()
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(page.get_by_role("dialog", name=re.compile("^AI 编辑助手"))).to_be_visible()
    page.get_by_role("textbox", name="AI 编辑指令").fill("保留我的草稿")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="AI 编辑", exact=True).click()
    expect(page.get_by_role("textbox", name="AI 编辑指令")).to_have_value("保留我的草稿")


@pytest.mark.parametrize("scene", ["outline", "speech", "share", "library", "image-preview", "template"])
def test_dark_dialogs_keep_native_fields_usable(ui_page, scene):
    page, load = ui_page
    setup(page, load)
    dialog = open_scene(page, scene)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=f"artifacts/ui-redesign/dialog-{scene}.png", full_page=True)
    expect(dialog).to_be_visible()


@pytest.mark.parametrize("template,path", [("pages/home/index.html", "/home"), ("pages/project/project_dashboard.html", "/dashboard"), ("pages/project/projects_list.html", "/projects"), ("pages/auth/login.html", "/auth/login")])
def test_shared_page_palette_is_visible(ui_page, template, path):
    page, load = ui_page
    load(template, path=path)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=f"artifacts/ui-redesign/page-{path.rsplit('/', 1)[-1]}.png", full_page=True)
