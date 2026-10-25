"""Partially successful PPTX analysis must remain usable and explicit."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_templates_ui import PACKAGES, management, template_api


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_partial_analysis_keeps_success_selected_and_failed_page_for_review(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    state = template_api(page)
    management(page, load, "packages")
    page.get_by_role("button", name="从 PPTX 创建", exact=True).click()
    dialog = page.get_by_role("dialog", name="从 PPTX 创建模板包", exact=True)
    dialog.locator(".native-ant-file input[type=file]").set_input_files(
        {
            "name": "partial.pptx",
            "mimeType": "application/octet-stream",
            "buffer": b"isolated fixture",
        }
    )

    def page_data(n, failed):
        return dict(
            slide=n,
            hidden=False,
            family="cover",
            review_required=failed,
            preview="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'/>",
            candidates=[
                dict(
                    id="title-1",
                    kind="text",
                    text="标题",
                    suggested="title",
                    capacity=40,
                )
            ],
            warnings=["模型请求失败，请检查后重试"] if failed else [],
        )

    page.route(
        "**/packages-pptx/analyze?*",
        lambda route: route.fulfill(
            body=json.dumps(
                dict(
                    type="complete",
                    result=dict(
                        slides=[page_data(1, False), page_data(2, True)],
                        warnings=[],
                        partial=True,
                        failures=[dict(slide=2, error="模型请求失败")],
                    ),
                )
            ),
            content_type="application/x-ndjson",
        ),
    )
    uploads = []

    def imported(route):
        uploads.append(route.request.post_data_buffer)
        route.fulfill(
            body=json.dumps(
                dict(
                    type="complete",
                    result=dict(
                        package=PACKAGES[0], warnings=[], failures=[], partial=False
                    ),
                )
            ),
            content_type="application/x-ndjson",
        )

    page.route("**/packages-pptx/import?*", imported)
    dialog.get_by_role("button", name="分析页面", exact=True).click()
    expect(dialog.locator(".package-status")).to_contain_text(
        "已完成 1 页识别，1 页需检查"
    )
    expect(dialog.locator(".pptx-page")).to_have_count(2)
    # Inspect the retained native values used to build the multipart options.
    picks = dialog.locator(".pptx-page summary > input[type=checkbox]")
    assert picks.evaluate_all("nodes=>nodes.map(node=>node.checked)") == [True, False]
    out = Path("artifacts/pptx-import-20261025")
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"partial-{width}.png"))
    dialog.get_by_role("button", name="生成模板包草稿", exact=True).click()
    expect(
        dialog.get_by_role("button", name="打开草稿，对照原稿", exact=True)
    ).to_be_visible()
    assert (
        len(uploads) == 1
        and b'"slide":1' in uploads[0]
        and b'"slide":2' not in uploads[0]
    )
    assert not state["writes"]  # Only isolated multipart responses above.


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_replica_defaults_to_one_upload_without_analysis_step(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    state = template_api(page)
    management(page, load, "packages")
    page.get_by_role("button", name="从 PPTX 创建", exact=True).click()
    dialog = page.get_by_role("dialog", name="从 PPTX 创建模板包", exact=True)
    dialog.locator(".native-ant-file input[type=file]").set_input_files(
        dict(name="simple.pptx", mimeType="application/octet-stream", buffer=b"fixture")
    )
    requests, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def replicate(route):
        requests.append(route.request)
        route.fulfill(
            content_type="application/x-ndjson",
            body="\n".join(
                json.dumps(event)
                for event in [
                    dict(type="progress", stage="bind", message="正在自动绑定原稿内容"),
                    dict(
                        type="complete",
                        result=dict(
                            package=PACKAGES[0], warnings=[], failures=[], partial=False
                        ),
                    ),
                ]
            ),
        )

    page.route("**/packages-pptx/*", replicate)
    start = dialog.get_by_role("button", name="开始复刻", exact=True)
    expect(start).to_be_visible()
    rect = start.bounding_box()
    assert rect and rect["x"] >= 0 and rect["x"] + rect["width"] <= width
    start.click()
    expect(
        dialog.get_by_role("button", name="打开草稿，对照原稿", exact=True)
    ).to_be_visible()
    assert len(requests) == 1 and "/replicate?" in requests[0].url
    assert b'name="name"' in requests[0].post_data_buffer
    assert not state["writes"] and not errors
    out = Path("artifacts/pptx-replica-20261025")
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"one-step-{width}.png"))


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_style_mode_posts_once_to_style_endpoint_without_analysis(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    state = template_api(page)
    management(page, load, "packages")
    page.get_by_role("button", name="从 PPTX 创建", exact=True).click()
    dialog = page.get_by_role("dialog", name="从 PPTX 创建模板包", exact=True)
    dialog.locator(".native-ant-file input[type=file]").set_input_files(
        dict(name="deck.pptx", mimeType="application/octet-stream", buffer=b"fixture")
    )
    dialog.get_by_role("combobox", name="导入方式", exact=True).click()
    page.locator(".ant-select-item-option", has_text="风格复刻").click()
    expect(dialog.locator('select[aria-label="导入方式"]')).to_have_value("style")
    expect(dialog.get_by_role("button", name="分析页面", exact=True)).to_be_hidden()
    expect(dialog.get_by_text("学习原稿的配色、字体", exact=False)).to_be_visible()
    requests, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def style(route):
        requests.append(route.request)
        route.fulfill(
            content_type="application/x-ndjson",
            body="\n".join(
                json.dumps(event)
                for event in [
                    dict(type="progress", stage="style", message="正在提取原稿风格"),
                    dict(
                        type="complete",
                        result=dict(
                            package=PACKAGES[0],
                            warnings=[],
                            failures=[dict(layout="process_5", error="文字区域太小")],
                            partial=True,
                        ),
                    ),
                ]
            ),
        )

    page.route("**/packages-pptx/*", style)
    dialog.get_by_role("button", name="开始复刻", exact=True).click()
    expect(
        dialog.get_by_role("button", name="打开草稿，对照原稿", exact=True)
    ).to_be_visible()
    expect(dialog.get_by_text("版式 process_5 未生成", exact=False)).to_be_visible()
    assert len(requests) == 1 and "/style?" in requests[0].url
    assert not state["writes"] and not errors
    out = Path("artifacts/pptx-style")
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"ui-style-{width}.png"))
