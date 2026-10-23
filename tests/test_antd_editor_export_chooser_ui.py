"""Purpose-based export selection calls the established exporters exactly once."""

from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_export_ui import install_renderer
from test_antd_editor_ui import HTML, setup

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


def chooser(page):
    page.get_by_role("button", name="导出", exact=True).click()
    return page.get_by_role("dialog", name="导出演示文稿", exact=True)


def goal(page, name):
    page.get_by_role("region", name="导出用途", exact=True).get_by_role(
        "button", name=name, exact=True
    ).click()


def intercept_commands(page):
    page.evaluate(
        """() => {
          const port=LandPPTEditorEngine, original=port.call;
          const methods=['exportSlidesToPptxClient','exportSvgPagesToPptx',
            'exportToPPTX','exportToPPTXAsImages','exportToPDF','downloadHTML'];
          window.chooserCalls=[];
          port.call=(name,...args)=>{
            if(!methods.includes(name)) return original(name,...args);
            chooserCalls.push([name,...args]);
            return new Promise(resolve=>{window.finishChosenExport=resolve});
          };
        }"""
    )


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("svg", [False, True])
def test_purpose_choices_are_bounded_read_only_and_keep_native_capabilities(
    ui_page, width, height, svg
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, svg=svg)
    before = page.evaluate("JSON.stringify(slidesData)")
    drawer = chooser(page)
    expect(drawer.get_by_text("2 页 · PPTX", exact=True)).to_be_visible()
    expect(drawer.get_by_role("radio", name="标准导出 PPTX", exact=True)).to_have_count(
        0
    )
    expect(
        drawer.get_by_role("radio", name="SVG 原生对象 PPTX", exact=True)
    ).to_have_count(1 if svg else 0)
    expect(
        drawer.get_by_role("radio", name="客户端导出 PPTX · Beta", exact=True)
    ).to_have_count(0 if svg else 1)
    goal(page, "保留版式")
    expect(
        drawer.get_by_role("radio", name="SVG 矢量保真 PPTX", exact=True)
    ).to_have_count(1 if svg else 0)
    expect(
        drawer.get_by_role("radio", name="图片形式 PPTX", exact=True)
    ).to_be_visible()
    expect(drawer).to_contain_text("页内文字和图形不能单独编辑")
    start = drawer.get_by_role("button", name="开始导出", exact=True)
    expect(start).to_be_in_viewport()
    start.focus()
    page.keyboard.press("Tab")
    assert drawer.evaluate("e=>e.contains(document.activeElement)")
    page.keyboard.press("Control+s")
    assert drawer.evaluate("e=>e.scrollWidth<=e.clientWidth")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    if not svg:
        output = Path("artifacts/editor-export-chooser-20261022")
        output.mkdir(parents=True, exist_ok=True)
        page.mouse.move(1, height - 2)
        page.screenshot(
            path=str(output / f"chooser-{width}x{height}.png"), animations="disabled"
        )
    goal(page, "阅读打印")
    expect(drawer.get_by_role("radio", name="导出 PDF", exact=True)).to_be_checked()
    expect(drawer.get_by_text("2 页 · PDF", exact=True)).to_be_visible()
    goal(page, "网页演示")
    expect(drawer).to_contain_text("HTML 文件包（ZIP）")
    expect(drawer.get_by_text("2 页 · ZIP", exact=True)).to_be_visible()
    goal(page, "继续编辑")
    page.keyboard.press("Escape")
    expect(drawer).not_to_be_visible()
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_focused()
    assert page.evaluate("JSON.stringify(slidesData)") == before
    assert not state["writes"] and not state["errors"]
    assert not any("/export/" in path for path in state["reads"])


@pytest.mark.parametrize(
    "svg,purpose,label,command",
    [
        (False, "继续编辑", "客户端导出 PPTX · Beta", ["exportSlidesToPptxClient"]),
        (False, "继续编辑", "标准导出 PPTX", ["exportToPPTX"]),
        (True, "继续编辑", "SVG 原生对象 PPTX", ["exportSvgPagesToPptx", "native"]),
        (True, "保留版式", "SVG 矢量保真 PPTX", ["exportSvgPagesToPptx", "vector"]),
        (False, "保留版式", "图片形式 PPTX", ["exportToPPTXAsImages"]),
        (False, "阅读打印", "导出 PDF", ["exportToPDF"]),
        (False, "网页演示", "下载 HTML", ["downloadHTML"]),
    ],
)
def test_explicit_start_dispatches_one_native_command_and_waits_for_completion(
    ui_page, svg, purpose, label, command
):
    page, load = ui_page
    state = setup(page, load, svg=svg, restricted=False)
    intercept_commands(page)
    drawer = chooser(page)
    goal(page, purpose)
    drawer.get_by_role("radio", name=label, exact=True).check()
    assert page.evaluate("chooserCalls") == []
    drawer.get_by_role("button", name="开始导出", exact=True).dblclick()
    expect(drawer).not_to_be_visible()
    trigger = page.get_by_role("button", name="导出", exact=True)
    expect(trigger).to_be_disabled()
    assert page.evaluate("chooserCalls") == [command]
    page.evaluate("finishChosenExport(true)")
    expect(trigger).to_be_enabled()
    drawer = chooser(page)
    expect(drawer.get_by_role("radio", name=label, exact=True)).to_be_checked()
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("dismiss", ["cancel", "Escape", "mask"])
def test_close_preserves_selection_and_returns_focus_without_exports(ui_page, dismiss):
    page, load = ui_page
    state = setup(page, load, restricted=False)
    drawer = chooser(page)
    drawer.get_by_role("radio", name="标准导出 PPTX", exact=True).check()
    if dismiss == "cancel":
        drawer.get_by_role("button", name="取消", exact=True).click()
    elif dismiss == "mask":
        page.locator(".ant-drawer-mask:visible").click(position=dict(x=2, y=2))
    else:
        page.keyboard.press(dismiss)
    expect(drawer).not_to_be_visible()
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_focused()
    drawer = chooser(page)
    expect(
        drawer.get_by_role("radio", name="标准导出 PPTX", exact=True)
    ).to_be_checked()
    assert not state["writes"] and not state["errors"]


def test_mode_change_removes_stale_choice_and_uses_current_native_capability(ui_page):
    page, load = ui_page
    state = setup(page, load, svg=True, restricted=False)
    intercept_commands(page)
    drawer = chooser(page)
    drawer.get_by_role("radio", name="标准导出 PPTX", exact=True).check()
    drawer.get_by_role("radio", name="SVG 原生对象 PPTX", exact=True).check()
    page.evaluate(
        "html=>{slidesData.forEach(s=>{s.html_content=html;s.render_mode='html'});LandPPTEditorEngine.changed()}",
        HTML,
    )
    expect(
        drawer.get_by_role("radio", name="SVG 原生对象 PPTX", exact=True)
    ).to_have_count(0)
    expect(
        drawer.get_by_role("radio", name="客户端导出 PPTX · Beta", exact=True)
    ).to_be_checked()
    expect(drawer).to_contain_text("页面模式已变化，请确认当前可用的导出方式")
    drawer.get_by_role("button", name="开始导出", exact=True).click()
    assert page.evaluate("chooserCalls") == [["exportSlidesToPptxClient"]]
    page.evaluate("finishChosenExport(true)")
    assert not state["writes"] and not state["errors"]


def test_actual_client_export_handoff_retains_progress_cancel_and_focus(ui_page):
    page, load = ui_page
    state = setup(page, load)
    install_renderer(page)
    before = page.locator("#slideFrame").get_attribute("srcdoc")
    drawer = chooser(page)
    drawer.get_by_role("button", name="开始导出", exact=True).click()
    progress = page.locator(".editor-ant-export-dialog")
    expect(progress).to_be_visible()
    page.wait_for_function("exportFixture.calls===1")
    expect(drawer).not_to_be_visible()
    page.keyboard.press("Escape")
    expect(progress).to_be_visible()
    progress.get_by_role("button", name="取消导出", exact=True).click()
    page.evaluate("releaseExport()")
    expect(progress).not_to_be_visible()
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_focused()
    assert page.locator("#slideFrame").get_attribute("srcdoc") == before
    assert not state["writes"] and not state["errors"]


def test_actual_html_export_keeps_filename_and_download_contract(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.route(
        "**/export/html",
        lambda route: route.fulfill(
            status=200,
            body=b"PK-fixture",
            headers={
                "Content-Type": "application/zip",
                "Content-Disposition": "attachment; filename*=UTF-8''%E6%BC%94%E7%A4%BA.zip",
            },
        ),
    )
    drawer = chooser(page)
    goal(page, "网页演示")
    with page.expect_download() as event:
        drawer.get_by_role("button", name="开始导出", exact=True).click()
    assert event.value.suggested_filename == "演示.zip"
    expect(drawer).not_to_be_visible()
    assert not state["writes"] and not state["errors"]


def test_actual_pdf_choice_starts_existing_async_endpoint(ui_page):
    page, load = ui_page
    state = setup(page, load)
    requests = []
    page.evaluate(
        "()=>{window.chooserDownloads=[];window.triggerFileDownload=url=>chooserDownloads.push(url)}"
    )

    def start(route):
        requests.append((route.request.method, route.request.post_data))
        route.fulfill(json={"download_url": "/delivery-fixture.pdf"})

    page.route("**/export/pdf/async", start)
    drawer = chooser(page)
    goal(page, "阅读打印")
    drawer.get_by_role("button", name="开始导出", exact=True).click()
    page.wait_for_function("chooserDownloads.length===1")
    assert requests == [("POST", None)]
    assert page.evaluate("chooserDownloads") == ["/delivery-fixture.pdf"]
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_enabled()
    assert not state["writes"] and not state["errors"]


def test_empty_editor_cannot_open_export_chooser(ui_page):
    page, load = ui_page
    state = setup(page, load, empty=True)
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_disabled()
    assert not state["writes"] and not state["errors"]


def test_save_in_progress_blocks_start_without_discarding_canvas_edits(ui_page):
    page, load = ui_page
    state = setup(page, load)
    held = []
    page.route("**/slides/*/save", lambda route: held.append(route))
    page.get_by_role("toolbar").get_by_title("代码", exact=True).click()
    source = HTML.replace("原始演示内容", "保存后再导出的内容")
    page.locator("#codeEditor").fill(source)
    page.get_by_role("button", name="保存", exact=True).click()
    drawer = chooser(page)
    expect(drawer).to_contain_text("正在保存，完成后即可导出")
    expect(drawer.get_by_role("button", name="开始导出", exact=True)).to_be_disabled()
    assert len(held) == 1
    assert held[0].request.post_data_json["html_content"] == source
    page.keyboard.press("Control+s")
    held[0].fulfill(json=dict(success=True))
    expect(drawer.get_by_role("button", name="开始导出", exact=True)).to_be_enabled()
    drawer.get_by_role("button", name="取消", exact=True).click()
    assert len(held) == 1
    expect(page.locator("#codeEditor")).to_have_value(source)
    assert not state["writes"] and not state["errors"]
