"""Native multi-page outline draft and atomic save UI, with isolated requests."""

import copy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_documents_ui import panel, revision
from test_antd_editor_outline_navigation_ui import directory, navigation_setup


def batch_setup(page, load, **options):
    state = navigation_setup(page, load, **options)
    state.update(
        batch_reads=[],
        batch_writes=[],
        batch_fail=False,
        batch_read_fail=False,
        batch_editable=True,
        hold=False,
        held=None,
        malformed=False,
    )

    def document(index):
        outline = copy.deepcopy(state["outlines"][index])
        return dict(
            slide_index=index,
            slide_id=f"stable-{index}",
            outline=outline,
            outline_revision=revision(outline),
        )

    def commit(body):
        for row in body["pages"]:
            state["outlines"][row["slide_index"]].update(row["changes"])
        docs = [document(row["slide_index"]) for row in body["pages"]]
        if state["malformed"]:
            docs = [docs[0]] * len(docs)
        return dict(success=True, project_revision="b" * 64, pages=docs, editable=True)

    state["commit"] = commit

    def endpoint(route):
        request = route.request
        if request.method == "GET":
            indices = [
                int(value) for value in parse_qs(urlsplit(request.url).query)["indices"]
            ]
            state["batch_reads"].append(indices)
            if state["batch_read_fail"]:
                route.fulfill(status=503, json=dict(detail="读取服务暂时不可用"))
            else:
                route.fulfill(
                    json=dict(
                        success=True,
                        project_revision="a" * 64,
                        pages=[document(index) for index in indices],
                        editable=state["batch_editable"],
                    )
                )
        else:
            body = request.post_data_json
            state["batch_writes"].append(body)
            if state["hold"]:
                state["held"] = route
            elif state["batch_fail"]:
                route.fulfill(
                    status=409,
                    json=dict(detail="第 6 页已更新；本批未保存，草稿已保留"),
                )
            else:
                route.fulfill(json=commit(body))

    page.route("**/editor-outline-batch*", endpoint)
    panel(page, "目录")
    return state


def check_page(page, title):
    node = (
        directory(page)
        .locator(".ant-tree-treenode")
        .filter(has=page.get_by_text(title, exact=True))
    )
    node.locator(".ant-tree-checkbox").click()


def open_batch(page):
    directory(page).get_by_role("button", name="批量编辑", exact=True).click()
    check_page(page, "封面")
    # Selection must survive filtering away an already checked page.
    search = directory(page).get_by_role("textbox", name="搜索文稿目录", exact=True)
    search.fill("职责")
    check_page(page, "流程与职责")
    expect(directory(page).get_by_text("已选 2 页", exact=True)).to_be_visible()
    directory(page).get_by_role("button", name="编辑选中页", exact=True).click()
    return page.get_by_role("dialog", name="批量编辑大纲 · 2 页", exact=True)


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
@pytest.mark.parametrize("svg", [False, True])
def test_batch_preview_failure_retry_and_save_preserve_artwork(
    ui_page, width, height, svg
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = batch_setup(page, load, svg=svg)
    original = page.evaluate("slidesData.map(slide=>slide.html_content)")
    drawer = open_batch(page)
    first = drawer.get_by_role("textbox", name="第 1 页标题", exact=True)
    expect(first).to_have_value("封面")
    assert state["batch_reads"] == [[0, 5]]
    drawer.get_by_role("textbox", name="标题前缀", exact=True).fill("计划 · ")
    drawer.get_by_role("button", name="应用前缀", exact=True).click()
    expect(first).to_have_value("计划 · 封面")
    drawer.get_by_role("combobox", name="统一页面类型", exact=True).click()
    page.locator(".ant-select-dropdown:visible").get_by_text(
        "章节过渡页", exact=True
    ).click()
    assert not state["batch_writes"]
    state["batch_fail"] = True
    save = drawer.get_by_role("button", name="保存 2 页修改", exact=True)
    save.click()
    expect(
        drawer.get_by_text("第 6 页已更新；本批未保存，草稿已保留", exact=True)
    ).to_be_visible()
    expect(first).to_have_value("计划 · 封面")
    save.focus()
    page.keyboard.press("Tab")
    assert drawer.evaluate("e=>e.contains(document.activeElement)")
    expect(save).to_be_in_viewport()
    assert drawer.evaluate("e=>e.scrollWidth<=e.clientWidth")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    if not svg:
        output = Path("artifacts/editor-outline-batch-20261022")
        output.mkdir(parents=True, exist_ok=True)
        page.mouse.move(width - 5, height - 5)
        page.screenshot(path=str(output / f"batch-{width}.png"), animations="disabled")
    state["batch_fail"] = False
    save.click()
    expect(drawer).not_to_be_visible()
    expect(
        directory(page).get_by_role("button", name="编辑选中页", exact=True)
    ).to_be_focused()
    directory(page).get_by_role("button", name="定位当前页", exact=True).click()
    expect(directory(page).get_by_role("status")).to_contain_text("4 个章节")
    expect(directory(page).get_by_text("计划 · 封面", exact=True)).to_be_visible()
    assert page.evaluate("slidesData.map(slide=>slide.html_content)") == original
    assert not state["writes"] and not state["document_writes"] and not state["errors"]
    body = state["batch_writes"][-1]
    assert body["project_revision"] == "a" * 64
    assert [item["slide_index"] for item in body["pages"]] == [0, 5]
    assert [item["changes"] for item in body["pages"]] == [
        dict(title="计划 · 封面", slide_type="transition"),
        dict(title="计划 · 流程与职责", slide_type="transition"),
    ]


def test_read_retry_task_lock_and_dirty_close_keep_explicit_control(ui_page):
    page, load = ui_page
    state = batch_setup(page, load)
    state["batch_read_fail"] = True
    drawer = open_batch(page)
    expect(drawer.get_by_text("读取服务暂时不可用", exact=True)).to_be_visible()
    state["batch_read_fail"], state["batch_editable"] = False, False
    drawer.get_by_role("button", name="重新读取", exact=True).click()
    editor = drawer.get_by_role("textbox", name="第 1 页标题", exact=True)
    expect(editor).to_be_disabled()
    state["batch_editable"] = True
    drawer.get_by_role("button", name="重新读取", exact=True).click()
    expect(editor).to_be_enabled()
    editor.fill("保留的草稿")
    page.keyboard.press("Escape")
    confirm = page.get_by_role("dialog", name="放弃本次批量修改？", exact=True)
    confirm.get_by_role("button", name="继续编辑", exact=True).click()
    expect(editor).to_have_value("保留的草稿")
    drawer.get_by_role("button", name="取消", exact=True).click()
    page.get_by_role("button", name="放弃修改", exact=True).click()
    expect(drawer).not_to_be_visible()
    assert not state["batch_writes"] and not state["errors"]


def test_existing_text_draft_blocks_bulk_entry_without_losing_draft(ui_page):
    page, load = ui_page
    state = batch_setup(page, load)
    panel(page, "大纲")
    editor = page.get_by_role("textbox", name="大纲标题", exact=True)
    expect(editor).to_have_value("封面")
    editor.fill("单页未保存修改")
    panel(page, "目录")
    expect(
        directory(page).get_by_role("button", name="批量编辑", exact=True)
    ).to_be_disabled()
    panel(page, "大纲")
    expect(editor).to_have_value("单页未保存修改")
    assert not state["batch_reads"] and not state["batch_writes"]


def test_pending_batch_cannot_close_or_submit_again_and_shortcut_targets_batch(ui_page):
    page, load = ui_page
    state = batch_setup(page, load)
    drawer = open_batch(page)
    editor = drawer.get_by_role("textbox", name="第 1 页标题", exact=True)
    expect(editor).to_have_value("封面")
    editor.fill("快捷键批量保存")
    state["hold"] = True
    editor.press("Control+s")
    expect(drawer.get_by_role("button", name="取消", exact=True)).to_be_disabled()
    page.keyboard.press("Escape")
    expect(drawer).to_be_visible()
    page.keyboard.press("Control+s")
    assert len(state["batch_writes"]) == 1 and state["held"] is not None
    state["held"].fulfill(json=state["commit"](state["batch_writes"][0]))
    expect(drawer).not_to_be_visible()
    assert not state["writes"] and not state["document_writes"] and not state["errors"]


def test_unconfirmed_receipt_keeps_all_drafts_until_user_reloads(ui_page):
    page, load = ui_page
    state = batch_setup(page, load)
    drawer = open_batch(page)
    editor = drawer.get_by_role("textbox", name="第 1 页标题", exact=True)
    expect(editor).to_have_value("封面")
    drawer.get_by_role("textbox", name="标题前缀", exact=True).fill("需核对 · ")
    drawer.get_by_role("button", name="应用前缀", exact=True).click()
    state["malformed"] = True
    drawer.get_by_role("button", name="保存 2 页修改", exact=True).click()
    expect(
        drawer.get_by_text(
            "服务器已响应，请重新读取核对保存结果；当前草稿已保留", exact=True
        )
    ).to_be_visible()
    expect(editor).to_have_value("需核对 · 封面")
    assert page.evaluate("slidesData[0].title") == "封面"
    assert not state["errors"]
