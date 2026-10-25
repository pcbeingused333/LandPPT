"""Remaining wizard and package surfaces: real controllers with isolated APIs."""

import json
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, generator_page, ui_page  # noqa: F401
from test_antd_templates_ui import HTML, management, template_api
from test_antd_template_wizard_ui import setup_wizard

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


@pytest.fixture
def package_page(ui_page):
    page, load = ui_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = template_api(page)
    for package in state["packages"]:
        for component in package["manifest"]["components"]:
            component.update(
                blocks=dict(minimum=0, maximum=4),
                metrics=dict(minimum=0, maximum=0),
                images=dict(minimum=0, maximum=1),
            )
    management(page, load, "packages")
    page.get_by_role("button", name="编辑草稿", exact=True).first.click()
    expect(page.locator(".package-ant-workspace")).to_be_visible()
    return page, state, errors


def fits(page, locator):
    box = locator.bounding_box()
    assert box
    viewport = page.viewport_size
    assert box["x"] >= 0 and box["y"] >= 0, box
    assert box["x"] + box["width"] <= viewport["width"] + 1, box
    assert box["y"] + box["height"] <= viewport["height"] + 1, box
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width,height", SIZES)
def test_package_workspace_has_ant_controls_and_bounded_footer(
    package_page, width, height
):
    page, _, errors = package_page
    page.set_viewport_size(dict(width=width, height=height))
    fits(page, page.get_by_role("button", name="校验并发布", exact=True).last)
    fits(page, page.get_by_role("button", name="AI 修改此页", exact=True))
    if width <= 760:
        page.get_by_text("AI 编辑", exact=True).click()
    page.get_by_role("textbox", name="整套模板修改要求", exact=True).fill(
        "统一标题字号"
    )
    fits(page, page.get_by_role("button", name="发送", exact=True))
    assert (
        page.locator(".pw-chat-form textarea.native-ant-source").input_value()
        == "统一标题字号"
    )
    assert not errors, errors


@pytest.mark.parametrize("width,height", SIZES)
def test_free_template_wizard_keeps_confirmation_visible(ui_page, width, height):
    page, load = ui_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size(dict(width=width, height=height))
    _, dialog = setup_wizard(page, load)
    expect(dialog).to_be_visible()
    fits(page, dialog.get_by_role("button", name="确认并开始生成PPT", exact=True))
    fits(page, dialog.get_by_role("button", name="取消", exact=True))
    assert (
        dialog.locator('iframe[title="自由模板预览"]')
        .get_attribute("srcdoc")
        .endswith("</html>")
    )
    dialog.get_by_role("button", name="取消", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert not errors, errors


def test_package_rename_escape_keeps_workspace_and_enter_preserves_patch(package_page):
    page, state, errors = package_page
    package = state["packages"][0]
    page.route("**/packages/11", lambda route: route.fulfill(json=package))
    page.get_by_role("button", name="重命名", exact=True).last.click()
    field = page.get_by_role("textbox", name="模板包名称", exact=True)
    expect(field).to_be_visible()
    field.fill("取消的名称")
    field.press("Escape")
    expect(page.locator(".package-ant-workspace")).to_be_visible()
    expect(field).not_to_be_visible()
    assert not state["writes"]
    page.get_by_role("button", name="重命名", exact=True).last.click()
    field.fill("新的模板包名称")
    field.press("Enter")
    page.wait_for_timeout(150)
    assert state["writes"][0][:3] == (
        "/api/global-master-templates/package-templates/1",
        "PATCH",
        {"name": "新的模板包名称"},
    )
    assert not errors, errors


def test_nested_description_failure_keeps_value_and_retry_submits_original_form(
    package_page,
):
    page, state, errors = package_page
    package = state["packages"][0]
    calls = []

    def patch(route):
        calls.append(route.request.post_data_json)
        route.fulfill(
            status=500 if len(calls) == 1 else 200, json={"detail": "保存失败"}
        )

    page.route("**/package-templates/1", patch)
    page.route("**/packages/11", lambda route: route.fulfill(json=package))
    page.get_by_role("button", name="编辑描述", exact=True).last.click()
    dialog = page.get_by_role("dialog", name="编辑模板包描述", exact=True)
    field = dialog.get_by_role("textbox", name="描述", exact=True)
    field.fill("新的用途与风格")
    dialog.get_by_role("button", name="保存", exact=True).click()
    expect(dialog).to_contain_text("保存失败")
    expect(field).to_have_value("新的用途与风格")
    dialog.get_by_role("button", name="保存", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert calls == [{"description": "新的用途与风格"}] * 2
    expect(page.locator(".package-ant-workspace")).to_be_visible()
    assert not errors, errors


@pytest.mark.parametrize("width,height", SIZES)
def test_package_streaming_retains_partial_reply_and_draft_on_failure(
    package_page, width, height
):
    page, _, errors = package_page
    page.set_viewport_size(dict(width=width, height=height))
    if width <= 760:
        page.get_by_text("AI 编辑", exact=True).click()
    page.evaluate(
        """() => {
      const original = window.fetch;
      window.calls = [];
      window.fetch = (url, options) => {
        if (!String(url).endsWith('/edit')) return original(url, options);
        window.calls.push(JSON.parse(options.body));
        return Promise.resolve(new Response(new ReadableStream({start(controller) {
          window.editEvent = item => controller.enqueue(new TextEncoder().encode('data: '+JSON.stringify(item)+'\\n\\n'));
        }}), {headers:{'Content-Type':'text/event-stream'}}));
      };
    }"""
    )
    field = page.get_by_role("textbox", name="整套模板修改要求", exact=True)
    field.fill("添加图文页")
    field.press("Control+Enter")
    page.wait_for_function("window.calls.length === 1")
    page.evaluate(
        "() => { window.editEvent({type:'reply',segment_id:'plan',text:'先保留封面。',reset:true}); }"
    )
    expect(page.locator(".pw-round-reply")).to_have_text("先保留封面。")
    expect(page.get_by_role("button", name="发送", exact=True)).to_be_disabled()
    expect(
        page.get_by_role("button", name="校验并发布", exact=True).last
    ).to_be_disabled()
    page.evaluate("() => { window.editEvent({type:'error',message:'修改未保存'}); }")
    expect(page.locator(".pw-round.is-error")).to_contain_text("修改未保存")
    expect(field).to_have_value("添加图文页")
    expect(page.locator(".pw-round-reply")).to_have_text("先保留封面。")
    expect(page.get_by_role("button", name="发送", exact=True)).to_be_enabled()
    fits(page, page.get_by_role("button", name="发送", exact=True))
    assert not errors, errors


@pytest.mark.parametrize("width,height", SIZES)
def test_pptx_analyser_ant_slots_keep_import_payload_and_fixed_footer(
    package_page, width, height
):
    page, state, errors = package_page
    page.get_by_role("dialog").get_by_role(
        "button", name="关闭", exact=True
    ).first.click()
    page.set_viewport_size(dict(width=width, height=height))
    page.get_by_role("button", name="从 PPTX 创建", exact=True).click()
    dialog = page.get_by_role("dialog", name="从 PPTX 创建模板包", exact=True)
    page.locator(".native-ant-file input[type=file]").set_input_files(
        dict(
            name="demo.pptx",
            mimeType="application/octet-stream",
            buffer=b"isolated-test",
        )
    )
    candidate = dict(
        id="title-1", kind="text", text="原稿标题", suggested="title", capacity=40
    )
    result = dict(
        warnings=[],
        slides=[
            dict(
                slide=1,
                family="cover",
                hidden=False,
                review_required=False,
                preview="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'/>",
                candidates=[candidate],
                warnings=[],
            )
        ],
    )
    page.route(
        "**/packages-pptx/analyze?*",
        lambda route: route.fulfill(
            body=json.dumps(dict(type="complete", result=result)) + "\n",
            content_type="application/x-ndjson",
        ),
    )
    uploads = []

    def import_file(route):
        uploads.append(route.request.post_data_buffer)
        route.fulfill(
            body=json.dumps(
                dict(
                    type="complete",
                    result=dict(
                        package=state["packages"][0],
                        warnings=[],
                        failures=[],
                        partial=False,
                    ),
                )
            )
            + "\n",
            content_type="application/x-ndjson",
        )

    page.route("**/packages-pptx/import?*", import_file)
    dialog.get_by_role("button", name="分析页面", exact=True).click()
    expect(
        dialog.get_by_role("button", name="生成模板包草稿", exact=True)
    ).to_be_visible()
    page.locator(".pptx-page summary").click()
    role = dialog.get_by_role("combobox", name="原稿标题的用途", exact=True)
    expect(role).to_be_visible()
    fits(page, dialog.get_by_role("button", name="生成模板包草稿", exact=True))
    dialog.get_by_role("button", name="生成模板包草稿", exact=True).click()
    expect(
        dialog.get_by_role("button", name="打开草稿，对照原稿", exact=True)
    ).to_be_visible()
    fits(page, dialog.get_by_role("button", name="打开草稿，对照原稿", exact=True))
    assert len(uploads) == 1
    assert (
        b'"mode":"replica"' in uploads[0]
        and b'"bindings":{"title-1":"title"}' in uploads[0]
    )
    assert not errors, errors


def test_wizard_cancel_returns_to_start_without_confirm_write(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load, cached=HTML)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    dialog.get_by_role("button", name="取消", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    assert not state["template_writes"] and page.evaluate("testStreams.length") == 0


def test_wizard_confirmation_starts_once_with_library_values(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load, cached=HTML)
    dialog.get_by_role("checkbox").check()
    dialog.get_by_role("textbox", name="模板名称", exact=True).fill("团队模板")
    dialog.get_by_role("button", name="确认并开始生成PPT", exact=True).click()
    page.wait_for_function("testStreams.length === 1")
    assert len(state["template_writes"]) == 1
    assert state["template_writes"][0][1] == dict(
        save_to_library=True, template_name="团队模板", html_template=HTML
    )
    expect(dialog).not_to_be_visible()


@pytest.mark.parametrize("width,height", SIZES)
def test_error_page_is_ant_and_long_error_remains_bounded(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    error = "<script>window.injected=true</script>" + "LongError" * 100
    load("error.html", error=error)
    expect(page.get_by_role("heading", name="页面处理失败")).to_be_visible()
    expect(page.locator(".app-error-page pre")).to_have_text(error)
    assert not page.evaluate("!!window.injected")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width,height", SIZES)
def test_shell_notice_and_notifications_are_ant_and_read_request_is_unchanged(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    page.route(
        "**/community/public-settings",
        lambda route: route.fulfill(
            json=dict(
                site_notice=dict(
                    active=True, title="公告", message="服务通知" * 30, level="info"
                )
            )
        ),
    )
    page.route(
        "**/notifications/unread-count",
        lambda route: route.fulfill(json=dict(unread_count=1)),
    )
    page.route(
        "**/notifications?*",
        lambda route: route.fulfill(
            json=dict(
                unread_count=1,
                notifications=[
                    dict(
                        id="notice-1",
                        title="项目已完成",
                        body="生成结果已保存" * 30,
                        created_at=1,
                        is_read=False,
                    )
                ],
            )
        ),
    )
    writes = []
    page.route(
        "**/notifications/notice-1/read",
        lambda route: (
            writes.append(route.request.method),
            route.fulfill(json=dict(unread_count=0)),
        ),
    )
    load("pages/project/project_dashboard.html")
    expect(page.locator(".app-announcement")).to_contain_text("公告")
    trigger = page.get_by_role("button", name="通知", exact=True)
    trigger.click()
    dialog = page.get_by_role("dialog", name="通知", exact=True)
    expect(dialog).to_be_visible()
    fits(page, dialog)
    dialog.get_by_role("button", name="项目已完成", exact=False).click()
    page.wait_for_timeout(100)
    assert writes == ["POST"]
    assert page.locator("#navNotificationBadge").get_attribute("hidden") is not None
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert trigger.evaluate("node => node === document.activeElement")


def test_notification_read_all_failure_uses_ant_message_and_keeps_retry(ui_page):
    page, load = ui_page
    page.route(
        "**/notifications/unread-count",
        lambda route: route.fulfill(json=dict(unread_count=1)),
    )
    page.route(
        "**/notifications?*",
        lambda route: route.fulfill(
            json=dict(
                unread_count=1,
                notifications=[dict(id="retry", title="生成已完成", is_read=False)],
            )
        ),
    )
    writes = []
    page.route(
        "**/notifications/read-all",
        lambda route: (
            writes.append(route.request.method),
            route.fulfill(status=500, json=dict(detail="failed")),
        ),
    )
    load("pages/project/project_dashboard.html")
    page.get_by_role("button", name="通知", exact=True).click()
    dialog = page.get_by_role("dialog", name="通知", exact=True)
    dialog.get_by_role("button", name="全部已读", exact=True).click()
    expect(page.locator(".ant-message-notice").last).to_contain_text(
        "操作失败，请稍后重试"
    )
    expect(dialog.get_by_role("button", name="全部已读", exact=True)).to_be_enabled()
    expect(dialog).to_contain_text("生成已完成")
    assert writes == ["POST"]
