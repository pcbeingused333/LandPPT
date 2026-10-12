"""PPTX conversion UI follows the native exporter, progress and abort signal."""

import re

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import setup

SIZES = [(1910, 915), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


def show_export(page, phase="convert", cancel=True):
    states = {
        "prepare": [
            "cog",
            "spinning",
            "正在导出 PPTX",
            "加载图标导出规则...",
            3,
            "准备中...",
        ],
        "convert": [
            "cog",
            "spinning",
            "正在导出单页 PPTX",
            "",
            47,
            "正在处理第 1/1 页: 实施计划",
        ],
        "package": [
            "cog",
            "spinning",
            "正在导出 PPTX",
            "",
            94,
            "正在生成 PPTX 文件...",
        ],
        "cancelling": [
            "ban",
            "",
            "正在取消导出",
            "请稍候，正在终止当前客户端导出任务...",
            47,
            "取消中...",
        ],
        "error": [
            "exclamation-circle",
            "error",
            "导出失败",
            "无法加载页面中的图片资源，请检查图片链接后重新导出。",
            0,
            "请关闭此窗口后重试",
        ],
    }
    page.evaluate(
        "args => {updateExportUI(...args);showExportOverlay()}", states[phase]
    )
    page.evaluate(
        "args => updateExportCancelButton(args[0],args[1],args[1]?'正在取消...':'取消导出')",
        [cancel and phase != "error", phase == "cancelling"],
    )
    dialog = page.locator(".editor-ant-export-dialog")
    expect(dialog).to_be_visible()
    return dialog


def install_renderer(page, mode="pause"):
    # Keep the real controller, DOM stream, native UI and AbortController.
    # The external renderer/expensive font-resource waits are isolated here.
    page.evaluate(
        """mode => {
          window.exportFixture = {mode, calls:0, bodies:[], aborted:0, options:null};
          window.ensureIframeHasLatestContent = (frame, html) => new Promise(resolve => {
            frame.onload = () => resolve(true); frame.srcdoc = html;
          });
          for (const name of ['waitForDocumentFontsReady','waitForDocumentImagesReady',
            'waitForFormulaRenderReady','waitForCanvasPaintReady','prepareClientExportDynamicResources','waitForAnimationFrames']) {
            window[name] = async () => {};
          }
          window.ensureDomToPptxReadyForExport = async () => ({
            setIconRules() {},
            async exportToPptx(stream, options) {
              const f = exportFixture; f.calls++;
              f.options = {fileName:options.fileName,autoEmbedFonts:options.autoEmbedFonts,
                svgAsVector:options.svgAsVector,slideNotes:options.slideNotes};
              f.signal = options.signal;
              if (mode === 'fail') throw new Error('页面转换失败：图片链接无法访问');
              if (mode === 'pause') {
                await new Promise((resolve,reject) => {
                  options.signal.addEventListener('abort', () => f.aborted++, {once:true});
                  window.releaseExport = () => options.signal.aborted ? reject(options.signal.reason) : resolve();
                });
              }
              for await (const body of stream) f.bodies.push(body.outerHTML);
            }
          });
        }""",
        mode,
    )


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize(
    "phase", ["prepare", "convert", "package", "cancelling", "error"]
)
def test_export_dialog_states_are_bounded_with_one_visible_progress_and_footer(
    ui_page, width, height, phase
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load)
    original = page.locator("#slideFrame").get_attribute("srcdoc")
    dialog = show_export(page, phase)
    box = dialog.bounding_box()
    assert box["x"] >= 0 and box["y"] >= 0
    assert box["x"] + box["width"] <= width
    assert box["y"] + box["height"] <= height
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not page.locator("#exportOverlay > .export-modal").is_visible()
    expect(dialog.locator(".ant-modal-title")).to_have_count(1)
    footer = dialog.locator(".ant-modal-footer")
    assert footer.bounding_box()["y"] + footer.bounding_box()["height"] <= height
    if phase == "error":
        expect(dialog.get_by_role("progressbar")).to_have_count(0)
        expect(dialog.get_by_role("button", name="关闭", exact=True)).to_be_visible()
        expect(dialog).to_contain_text("图片资源")
    else:
        expect(dialog.get_by_role("progressbar")).to_have_count(1)
        expect(dialog.get_by_role("progressbar")).to_have_attribute(
            "aria-valuenow",
            str({"prepare": 3, "convert": 47, "package": 94, "cancelling": 47}[phase]),
        )
        cancel = dialog.get_by_role(
            "button",
            name="正在取消..." if phase == "cancelling" else "取消导出",
            exact=True,
        )
        expect(cancel).to_be_visible()
        if width <= 700:
            assert cancel.bounding_box()["height"] >= 44
        if phase == "cancelling":
            expect(cancel).to_be_disabled()
            expect(cancel).to_have_class(re.compile("ant-btn-loading"))
        page.keyboard.press("Escape")
        expect(dialog).to_be_visible()
    assert page.locator("#slideFrame").get_attribute("srcdoc") == original
    assert not state["errors"] and not state["writes"]


def test_progress_changes_without_changing_title_and_reports_real_stage(ui_page):
    page, load = ui_page
    state = setup(page, load)
    dialog = show_export(page, "prepare")
    for percent in [0, 17.2, 47.8, 88, 100]:
        page.evaluate(
            "p => updateExportUI(null,null,null,'',p,'正在处理第 2/4 页: 研发计划')",
            percent,
        )
        expect(dialog.get_by_role("progressbar")).to_have_attribute(
            "aria-valuenow", str(round(percent))
        )
        expect(dialog).to_contain_text("正在处理第 2/4 页")
    expect(dialog.locator(".ant-modal-title")).to_have_text("正在导出 PPTX")
    page.evaluate("updateExportUI(null,null,null,'',94,'正在生成 PPTX 文件...')")
    expect(dialog).to_contain_text("正在生成 PPTX 文件")
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("status", ["1/4", "4/4"])
def test_svg_progress_uses_native_completed_page_count(ui_page, status):
    page, load = ui_page
    state = setup(page, load, svg=True)
    show_export(page)
    page.evaluate(
        "status => updateExportUI(null,null,'正在导出 SVG 矢量保真 PPTX','正在转换 SVG 页面...',45,status)",
        status,
    )
    expect(page.locator(".editor-export-progress")).to_contain_text(
        f"已转换 {status.replace('/', ' / ')} 页"
    )
    assert not state["writes"] and not state["errors"]


def test_unknown_progress_and_reduced_motion_do_not_invent_percentage(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.emulate_media(reduced_motion="reduce")
    page.evaluate(
        "() => {showExportOverlay();document.getElementById('exportProgressBar').style.width='';}"
    )
    dialog = page.locator(".editor-ant-export-dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("处理中")
    expect(dialog.get_by_role("progressbar")).to_have_count(0)
    assert (
        dialog.locator(".anticon-spin").evaluate("e=>getComputedStyle(e).animationName")
        == "none"
    )
    assert not state["errors"] and not state["writes"]


@pytest.mark.parametrize("method", ["button", "Escape", "mask"])
def test_failure_has_clear_dismissal_and_restores_export_trigger(ui_page, method):
    page, load = ui_page
    state = setup(page, load)
    trigger = page.locator("[data-editor-export-trigger]")
    trigger.focus()
    dialog = show_export(page, "error")
    if method == "button":
        dialog.get_by_role("button", name="关闭", exact=True).click()
    elif method == "Escape":
        page.keyboard.press("Escape")
    else:
        page.locator(".ant-modal-wrap").click(position=dict(x=4, y=4))
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()
    assert not state["writes"] and not state["errors"]


def test_running_export_cannot_be_dismissed_or_cancelled_by_mask_or_escape(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.locator(".slide-thumbnail").nth(1).click(modifiers=["Control"])
    selected = page.evaluate("[...selectedSlideIndices]")
    dialog = show_export(page)
    page.keyboard.press("Escape")
    page.locator(".ant-modal-wrap").click(position=dict(x=4, y=4))
    page.evaluate("LandPPTEditorUI.dismissExport()")
    expect(dialog).to_be_visible()
    assert page.evaluate("[...selectedSlideIndices]") == selected
    assert not state["writes"] and not state["errors"]


def test_native_cancel_waits_for_abort_cleanup_and_does_not_duplicate_requests(ui_page):
    page, load = ui_page
    state = setup(page, load)
    install_renderer(page)
    page.evaluate("() => {window.exportPromise=exportSlidesToPptxClient()}")
    page.wait_for_function("exportFixture.calls===1")
    dialog = page.locator(".editor-ant-export-dialog")
    dialog.get_by_role("button", name="取消导出", exact=True).click()
    expect(dialog.locator(".ant-modal-title")).to_have_text("正在取消导出")
    expect(
        dialog.get_by_role("button", name="正在取消...", exact=True)
    ).to_be_disabled()
    assert page.evaluate("exportFixture.signal.aborted")
    assert page.evaluate("exportFixture.aborted") == 1
    assert page.evaluate("isClientExporting")
    page.evaluate("LandPPTEditorUI.cancelExport()")
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    assert page.evaluate("exportFixture.aborted") == 1
    page.evaluate("() => {releaseExport()}")
    page.wait_for_function("!isClientExporting && clientExportAbortController===null")
    expect(dialog).not_to_be_visible()
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("single", [False, True])
def test_native_export_success_preserves_page_source_and_speaker_notes(ui_page, single):
    page, load = ui_page
    state = setup(page, load)
    source = page.locator("#slideFrame").get_attribute("srcdoc")
    page.evaluate(
        "slidesData[1].html_content=slidesData[1].html_content.replace('原始演示内容','第二页导出内容')"
    )
    install_renderer(page, "success")
    page.evaluate(
        "options => {window.exportPromise=exportSlidesToPptxClient(options)}",
        dict(slideIndices=[1]) if single else {},
    )
    page.wait_for_function("exportFixture.calls===1 && !isClientExporting")
    expect(page.locator(".editor-ant-export-dialog")).not_to_be_visible()
    result = page.evaluate(
        "({bodies:exportFixture.bodies,options:exportFixture.options})"
    )
    assert len(result["bodies"]) == (1 if single else 2)
    assert "第二页导出内容" in result["bodies"][-1]
    assert result["options"]["autoEmbedFonts"] is True
    assert result["options"]["svgAsVector"] is False
    assert len(result["options"]["slideNotes"]) == (1 if single else 2)
    if single:
        assert "-P2-实施计划.pptx" in result["options"]["fileName"]
    assert page.locator("#slideFrame").get_attribute("srcdoc") == source
    assert not state["writes"] and not state["errors"]


def test_actual_native_failure_can_close_and_start_another_export(ui_page):
    page, load = ui_page
    state = setup(page, load)
    install_renderer(page, "fail")
    page.evaluate("() => {window.exportPromise=exportSlidesToPptxClient()}")
    dialog = page.locator(".editor-ant-export-dialog")
    expect(dialog).to_contain_text("页面转换失败：图片链接无法访问")
    dialog.get_by_role("button", name="关闭", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert not page.evaluate("isClientExporting")
    install_renderer(page)
    page.evaluate("() => {window.exportPromise=exportSlidesToPptxClient()}")
    page.wait_for_function("exportFixture.calls===1")
    expect(dialog.locator(".ant-modal-title")).to_have_text("正在导出 PPTX")
    dialog.get_by_role("button", name="取消导出", exact=True).click()
    page.evaluate("() => {releaseExport()}")
    expect(dialog).not_to_be_visible()
    assert not state["writes"] and not state["errors"]


def test_reopened_dialog_returns_to_its_new_origin_and_long_errors_stay_bounded(
    ui_page,
):
    page, load = ui_page
    state = setup(page, load)
    for index in [0, 1]:
        thumbnail = page.locator(".slide-thumbnail").nth(index)
        thumbnail.focus()
        dialog = show_export(page, "error")
        page.evaluate(
            "updateExportUI(null,null,null,'错误详情'.repeat(400),undefined,undefined)"
        )
        expect(dialog.locator(".editor-export-error-detail")).to_contain_text(
            "错误详情"
        )
        assert dialog.bounding_box()["height"] <= 868
        assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth")
        dialog.get_by_role("button", name="关闭", exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(thumbnail).to_be_focused()
    assert not state["writes"] and not state["errors"]


@pytest.mark.parametrize("mode", ["native", "vector"])
@pytest.mark.parametrize("cancelled", [False, True])
def test_svg_export_keeps_progress_abort_and_download_contract(
    ui_page, mode, cancelled
):
    page, load = ui_page
    state = setup(page, load, svg=True)
    original = page.locator("#slideFrame").get_attribute("srcdoc")
    page.evaluate(
        """() => {
      window.ensureDomToPptxReadyForExport = async () => ({});
      svgPptx.build = async (pages, mode, exporter, options) => {
        window.svgExportFixture = {count:pages.length, mode, signal:options.signal};
        options.onProgress(1, pages.length);
        await new Promise(resolve => {window.releaseSvgExport=resolve});
        if (options.signal.aborted) throw options.signal.reason;
        options.onProgress(pages.length, pages.length);
        return {blob:new Blob(['isolated renderer result']),stats:pages.map(() => ({texts:1,shapes:2,vectors:3}))};
      };
    }"""
    )
    page.evaluate("mode => {window.exportPromise=exportSvgPagesToPptx(mode)}", mode)
    dialog = page.locator(".editor-ant-export-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "45")
    expect(dialog).to_contain_text("已转换 1 / 2 页")
    assert page.evaluate("svgExportFixture.mode") == mode
    if cancelled:
        dialog.get_by_role("button", name="取消导出", exact=True).click()
        expect(
            dialog.get_by_role("button", name="正在取消...", exact=True)
        ).to_be_disabled()
        assert page.evaluate("svgExportFixture.signal.aborted")
        page.evaluate("() => {releaseSvgExport()}")
    else:
        with page.expect_download() as download:
            page.evaluate("() => {releaseSvgExport()}")
        assert download.value.suggested_filename.endswith(f"-SVG-{mode}.pptx")
    expect(dialog).not_to_be_visible()
    assert page.locator("#slideFrame").get_attribute("srcdoc") == original
    assert not state["writes"] and not state["errors"]
