"""Native Ant free-template preparation with isolated APIs and real page actions."""

import json
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_home_generator_ui import setup_workspace

HTML = '<html><body style="margin:0;width:1280px;height:720px;background:#e8eef5"><h1 style="padding:80px;font:64px sans-serif">项目协作计划</h1></body></html>'
NEXT = HTML.replace("项目协作计划", "新版协作计划")


def setup_wizard(page, load, cached=HTML):
    state = setup_workspace(page, load, mode="free")
    state.update(
        template=cached,
        template_writes=[],
        fail_confirm=False,
        fail_adjust=False,
        stream_error=False,
        template_status="ready",
        confirmed=False,
    )

    def api(route):
        request = route.request
        path = urlsplit(request.url).path
        if request.method == "POST":
            state["template_writes"].append((path, request.post_data_json))
        if path.endswith("/confirm"):
            if state["fail_confirm"]:
                route.fulfill(json=dict(success=False, error="模板保存失败，请重试"))
            else:
                state["template"] = request.post_data_json["html_template"]
                state["confirmed"] = True
                route.fulfill(json=dict(success=True))
        elif path.endswith("/adjust"):
            if state["fail_adjust"]:
                route.fulfill(json=dict(success=False, error="调整暂时不可用"))
            else:
                state["template"] = NEXT
                route.fulfill(
                    json=dict(
                        success=True,
                        template=dict(html_template=NEXT, template_name="协作计划"),
                    )
                )
        elif path.endswith("/generate"):
            event = (
                dict(type="error", message="生成暂时不可用")
                if state["stream_error"]
                else dict(
                    type="complete",
                    template=dict(html_template=NEXT, template_name="协作计划"),
                )
            )
            if not state["stream_error"]:
                state["template"] = NEXT
            route.fulfill(
                body="data: " + json.dumps(event, ensure_ascii=False) + "\n\n",
                content_type="text/event-stream",
            )
        else:
            route.fulfill(
                json=dict(
                    success=True,
                    confirmed=state["confirmed"],
                    status=state["template_status"],
                    template=(
                        dict(html_template=state["template"], template_name="协作计划")
                        if state["template"]
                        else None
                    ),
                )
            )

    page.route("**/free-template**", api)
    page.get_by_role("button", name="开始生成", exact=True).click()
    dialog = page.get_by_role("dialog", name="自由模板 · AI 设计", exact=True)
    expect(dialog).to_be_visible()
    return state, dialog


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (390, 844), (320, 568), (844, 390)]
)
def test_wizard_layout_and_fixed_confirmation_use_native_ant_controls(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state, dialog = setup_wizard(page, load)
    button = dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    expect(button).to_be_enabled()
    box = button.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert button.evaluate(
        "e => {const r=e.getBoundingClientRect(); return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}"
    )
    expect(dialog.get_by_role("tab", name="预览", exact=True)).to_be_visible()
    assert page.locator("#freeTemplateModal, .native-ant-content").count() == 0
    assert page.evaluate("typeof freeTemplateModalInstance === 'undefined'")
    assert page.evaluate(
        "typeof window.bootstrap === 'undefined' && typeof window.LandPPTGeneratorUI === 'undefined'"
    )
    assert not state["template_writes"] and not errors
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_cancel_then_reopen_preserves_source_and_library_fields_without_writes(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    dialog.get_by_role("tab", name="源代码", exact=True).click()
    dialog.get_by_role("textbox", name="模板 HTML 源码", exact=True).fill(NEXT)
    dialog.get_by_role("checkbox", name="保存到模板库", exact=True).check()
    dialog.get_by_role("textbox", name="模板名称", exact=True).fill("团队母版")
    dialog.get_by_role("button", name="取消", exact=True).click()
    expect(dialog).not_to_be_visible()
    start = page.get_by_role("button", name="开始生成", exact=True)
    expect(start).to_be_enabled()
    start.click()
    expect(dialog).to_be_visible()
    expect(
        dialog.get_by_role("textbox", name="模板 HTML 源码", exact=True)
    ).to_have_value(NEXT)
    expect(dialog.get_by_role("textbox", name="模板名称", exact=True)).to_have_value(
        "团队母版"
    )
    assert page.evaluate("testStreams.length") == 0 and not state["template_writes"]


def test_confirm_submits_unapplied_code_and_starts_one_slide_stream(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    dialog.get_by_role("tab", name="源代码", exact=True).click()
    dialog.get_by_role("textbox", name="模板 HTML 源码", exact=True).fill(NEXT)
    dialog.get_by_role("checkbox", name="保存到模板库", exact=True).check()
    dialog.get_by_role("textbox", name="模板名称", exact=True).fill("团队母版")
    dialog.get_by_role("button", name="确认并开始生成PPT", exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role("button", name="暂停", exact=True)).to_be_visible()
    assert state["template_writes"] == [
        (
            "/api/projects/ui-generator/free-template/confirm",
            dict(save_to_library=True, template_name="团队母版", html_template=NEXT),
        )
    ]
    assert page.evaluate("testStreams.length") == 1


def test_confirm_failure_stays_open_and_does_not_start_slides(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load)
    state["fail_confirm"] = True
    dialog.get_by_role("button", name="确认并开始生成PPT", exact=True).click()
    expect(dialog.get_by_role("alert").filter(has_text="模板保存失败")).to_be_visible()
    assert page.evaluate("testStreams.length") == 0
    assert len(state["template_writes"]) == 1
    state["fail_confirm"] = False
    dialog.get_by_role("button", name="确认并开始生成PPT", exact=True).click()
    expect(page.get_by_role("button", name="暂停", exact=True)).to_be_visible()
    assert page.evaluate("testStreams.length") == 1


def test_new_template_generates_once_and_stream_failure_has_no_automatic_retry(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load, cached=None)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    assert len(state["template_writes"]) == 1
    state["stream_error"] = True
    dialog.get_by_role("button", name="重新生成", exact=True).click()
    expect(
        dialog.get_by_role("alert").filter(has_text="生成暂时不可用")
    ).to_be_visible()
    assert len(state["template_writes"]) == 2
    assert page.evaluate("testStreams.length") == 0


def test_adjustment_warns_before_replacing_source_and_keeps_draft_on_cancel(ui_page):
    page, load = ui_page
    state, dialog = setup_wizard(page, load)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    dialog.get_by_role("tab", name="源代码", exact=True).click()
    dialog.get_by_role("textbox", name="模板 HTML 源码", exact=True).fill(NEXT)
    dialog.get_by_role("textbox", name="调整要求", exact=True).fill("增加留白")
    dialog.get_by_role("button", name="AI 调整模板", exact=True).click()
    confirmation = page.get_by_role("dialog", name="操作确认", exact=True)
    expect(confirmation).to_contain_text("替换未确认的源码修改")
    confirmation.get_by_role("button", name="取消", exact=True).click()
    expect(
        dialog.get_by_role("textbox", name="模板 HTML 源码", exact=True)
    ).to_have_value(NEXT)
    assert not state["template_writes"]


def test_adjust_failure_preserves_prompt_and_pagehide_ignores_late_confirmation(
    ui_page,
):
    page, load = ui_page
    state, dialog = setup_wizard(page, load)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    state["fail_adjust"] = True
    dialog.get_by_role("textbox", name="调整要求", exact=True).fill("增加留白")
    dialog.get_by_role("button", name="AI 调整模板", exact=True).click()
    expect(
        dialog.get_by_role("alert").filter(has_text="调整暂时不可用")
    ).to_be_visible()
    expect(dialog.get_by_role("textbox", name="调整要求", exact=True)).to_have_value(
        "增加留白"
    )
    dialog.get_by_role("button", name="取消", exact=True).click()
    page.get_by_role("button", name="开始生成", exact=True).click()
    expect(dialog).to_be_visible()
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));"
    )
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    assert page.evaluate("testStreams.length") == 0


def test_fullscreen_uses_original_template_and_escape_returns_to_wizard(ui_page):
    page, load = ui_page
    interactive = HTML.replace(
        "</body>",
        "<button onclick=\"this.textContent='已响应'\">预览交互</button></body>",
    )
    _, dialog = setup_wizard(page, load, cached=interactive)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    dialog.get_by_role("button", name="全屏预览模板", exact=True).click()
    fullscreen = page.get_by_role("dialog", name="自由模板全屏预览", exact=True)
    expect(fullscreen).to_be_visible()
    assert fullscreen.locator("iframe").get_attribute("srcdoc") == interactive
    fullscreen.frame_locator("iframe").get_by_role(
        "button", name="预览交互", exact=True
    ).click()
    expect(
        fullscreen.frame_locator("iframe").get_by_role(
            "button", name="已响应", exact=True
        )
    ).to_be_visible()
    fullscreen.locator(".ant-modal-close").focus()
    page.keyboard.press("Escape")
    expect(fullscreen).not_to_be_visible()
    expect(dialog).to_be_visible()


def test_closing_partial_template_stream_cancels_reader_without_automatic_retry(
    ui_page,
):
    page, load = ui_page
    page.add_init_script(
        """(() => {
      const original = window.fetch.bind(window); window.templateStreams = []; window.templateCancels = 0;
      window.fetch = (input, init) => String(input).endsWith('/free-template/generate')
        ? Promise.resolve(new Response(new ReadableStream({start(writer){templateStreams.push(writer)},cancel(){templateCancels++}}), {headers:{'Content-Type':'text/event-stream'}}))
        : original(input, init);
    })();"""
    )
    _, dialog = setup_wizard(page, load, cached=None)
    page.wait_for_function("templateStreams.length === 1")
    page.evaluate(
        "html => templateStreams[0].enqueue(new TextEncoder().encode('data: '+JSON.stringify({type:'preview',html_template:html})+'\\n\\n'))",
        HTML,
    )
    expect(dialog.locator('iframe[title="自由模板预览"]')).to_have_attribute(
        "srcdoc", HTML
    )
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_disabled()
    dialog.get_by_role("button", name="取消", exact=True).click()
    page.wait_for_function("templateCancels === 1")
    page.get_by_role("button", name="开始生成", exact=True).click()
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("上次请求尚未确认")
    assert page.evaluate("templateStreams.length") == 1


def test_pagehide_during_confirm_aborts_late_start_and_restores_start_button(ui_page):
    page, load = ui_page
    _, dialog = setup_wizard(page, load)
    expect(
        dialog.get_by_role("button", name="确认并开始生成PPT", exact=True)
    ).to_be_enabled()
    held = []
    page.route("**/free-template/confirm", lambda route: held.append(route))
    dialog.get_by_role("button", name="确认并开始生成PPT", exact=True).click()
    page.wait_for_timeout(50)
    assert len(held) == 1
    page.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));"
    )
    held[0].fulfill(json=dict(success=True))
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    assert page.evaluate("testStreams.length") == 0
