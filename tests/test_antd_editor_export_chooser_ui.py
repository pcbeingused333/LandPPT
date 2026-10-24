"""The export dropdown calls the established exporters exactly once."""

import re

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_export_ui import install_renderer
from test_antd_editor_ui import HTML, setup

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


def chooser(page):
    page.get_by_role("button", name="导出", exact=True).click()
    menu = page.locator(".editor-export-menu .ant-dropdown-menu")
    expect(menu).to_be_visible()
    return menu


def item(menu, label):
    return menu.get_by_role("menuitem", name=re.compile("^" + re.escape(label)))


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
def test_menu_lists_native_capabilities_without_starting_exports(
    ui_page, width, height, svg
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, svg=svg)
    before = page.evaluate("JSON.stringify(slidesData)")
    menu = chooser(page)
    expect(menu).to_contain_text("导出整份文稿 · 2 页")
    expect(item(menu, "标准导出 PPTX")).to_have_count(0)
    expect(item(menu, "SVG 原生对象 PPTX")).to_have_count(1 if svg else 0)
    expect(item(menu, "客户端导出 PPTX · Beta")).to_have_count(0 if svg else 1)
    expect(item(menu, "SVG 矢量保真 PPTX")).to_have_count(1 if svg else 0)
    expect(item(menu, "图片形式 PPTX")).to_be_visible()
    expect(item(menu, "导出 PDF")).to_be_visible()
    expect(menu).to_contain_text("HTML 文件包（ZIP）")
    expect(menu).to_contain_text("页内文字和图形不能单独编辑")
    box = menu.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_focused()
    assert page.evaluate("JSON.stringify(slidesData)") == before
    assert not state["writes"] and not state["errors"]
    assert not any("/export/" in path for path in state["reads"])


@pytest.mark.parametrize(
    "svg,label,command",
    [
        (False, "客户端导出 PPTX · Beta", ["exportSlidesToPptxClient"]),
        (False, "标准导出 PPTX", ["exportToPPTX"]),
        (True, "SVG 原生对象 PPTX", ["exportSvgPagesToPptx", "native"]),
        (True, "SVG 矢量保真 PPTX", ["exportSvgPagesToPptx", "vector"]),
        (False, "图片形式 PPTX", ["exportToPPTXAsImages"]),
        (False, "导出 PDF", ["exportToPDF"]),
        (False, "下载 HTML", ["downloadHTML"]),
    ],
)
def test_choice_dispatches_one_native_command_and_waits_for_completion(
    ui_page, svg, label, command
):
    page, load = ui_page
    state = setup(page, load, svg=svg, restricted=False)
    intercept_commands(page)
    menu = chooser(page)
    assert page.evaluate("chooserCalls") == []
    item(menu, label).dblclick()
    expect(menu).not_to_be_visible()
    trigger = page.get_by_role("button", name="导出", exact=True)
    expect(trigger).to_be_disabled()
    assert page.evaluate("chooserCalls") == [command]
    page.evaluate("finishChosenExport(true)")
    expect(trigger).to_be_enabled()
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("dismiss", ["Escape", "outside"])
def test_close_returns_focus_without_exports(ui_page, dismiss):
    page, load = ui_page
    state = setup(page, load, restricted=False)
    intercept_commands(page)
    menu = chooser(page)
    if dismiss == "outside":
        page.mouse.click(2, 2)
    else:
        page.keyboard.press(dismiss)
    expect(menu).not_to_be_visible()
    if dismiss == "Escape":
        expect(page.get_by_role("button", name="导出", exact=True)).to_be_focused()
    assert page.evaluate("chooserCalls") == []
    assert not state["writes"] and not state["errors"]


def test_mode_change_uses_current_native_capability(ui_page):
    page, load = ui_page
    state = setup(page, load, svg=True, restricted=False)
    intercept_commands(page)
    page.evaluate(
        "html=>{slidesData.forEach(s=>{s.html_content=html;s.render_mode='html'});LandPPTEditorEngine.changed()}",
        HTML,
    )
    menu = chooser(page)
    expect(item(menu, "SVG 原生对象 PPTX")).to_have_count(0)
    item(menu, "客户端导出 PPTX · Beta").click()
    assert page.evaluate("chooserCalls") == [["exportSlidesToPptxClient"]]
    page.evaluate("finishChosenExport(true)")
    assert not state["writes"] and not state["errors"]


def test_actual_client_export_handoff_retains_progress_cancel_and_focus(ui_page):
    page, load = ui_page
    state = setup(page, load)
    install_renderer(page)
    before = page.locator("#slideFrame").get_attribute("srcdoc")
    menu = chooser(page)
    item(menu, "客户端导出 PPTX · Beta").click()
    progress = page.locator(".editor-ant-export-dialog")
    expect(progress).to_be_visible()
    page.wait_for_function("exportFixture.calls===1")
    expect(menu).not_to_be_visible()
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
    menu = chooser(page)
    with page.expect_download() as event:
        item(menu, "下载 HTML").click()
    assert event.value.suggested_filename == "演示.zip"
    expect(menu).not_to_be_visible()
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
    menu = chooser(page)
    item(menu, "导出 PDF").click()
    page.wait_for_function("chooserDownloads.length===1")
    assert requests == [("POST", None)]
    assert page.evaluate("chooserDownloads") == ["/delivery-fixture.pdf"]
    expect(page.get_by_role("button", name="导出", exact=True)).to_be_enabled()
    assert not state["writes"] and not state["errors"]


def test_empty_editor_cannot_open_export_menu(ui_page):
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
    menu = chooser(page)
    expect(menu).to_contain_text("正在保存，完成后即可导出")
    expect(item(menu, "导出 PDF")).to_have_attribute("aria-disabled", "true")
    assert len(held) == 1
    assert held[0].request.post_data_json["html_content"] == source
    held[0].fulfill(json=dict(success=True))
    expect(item(menu, "导出 PDF")).not_to_have_attribute("aria-disabled", "true")
    page.keyboard.press("Escape")
    assert len(held) == 1
    expect(page.locator("#codeEditor")).to_have_value(source)
    assert not state["writes"] and not state["errors"]
