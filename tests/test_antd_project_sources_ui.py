"""Native material drawer: retryable drafts, keyboard and responsive layout."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_todo_ui import OUTLINE, multipart, setup


def open_sources(page, load, **options):
    state = setup(page, load, scene="outline", **options)
    state.update(
        source_reads=0,
        source_writes=[],
        source_fail=False,
        source_read_fail=False,
        source_editable=True,
    )
    snapshot = dict(
        revision="a" * 64,
        files=[dict(id="old-file-id", filename="研究资料" * 18 + ".txt")],
        urls=["https://example.invalid/old"],
        editable=True,
    )

    def endpoint(route):
        request = route.request
        if request.method == "GET":
            state["source_reads"] += 1
            if state["source_read_fail"]:
                route.fulfill(status=503, json=dict(detail="读取服务暂时不可用"))
            else:
                route.fulfill(
                    json=dict(
                        success=True,
                        sources={**snapshot, "editable": state["source_editable"]},
                    )
                )
        else:
            fields, files = multipart(request)
            state["source_writes"].append((fields, files))
            if state["source_fail"]:
                route.fulfill(
                    status=409, json=dict(detail="资料已在其他窗口更新，草稿已保留")
                )
            else:
                snapshot.update(
                    revision="b" * 64,
                    files=[
                        dict(id="new-file-id", filename=filename)
                        for filename, _ in files
                    ],
                    urls=fields["content_urls"].splitlines(),
                )
                route.fulfill(json=dict(success=True, sources=snapshot))

    page.route("**/projects/ui-todo/sources", endpoint)
    return state, snapshot


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
def test_material_drawer_failed_save_keeps_draft_then_updates_summary_without_generation(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state, snapshot = open_sources(page, load)
    page.get_by_role("button", name="管理资料", exact=True).click()
    drawer = page.get_by_role("dialog", name="管理参考资料", exact=True)
    expect(drawer.get_by_role("button", name="保存资料", exact=True)).to_be_disabled()
    drawer.get_by_role(
        "button", name="移除已存附件 " + snapshot["files"][0]["filename"], exact=True
    ).click()
    drawer.locator("input[type=file]").set_input_files(
        dict(name="replacement.txt", mimeType="text/plain", buffer=b"REPLACEMENT")
    )
    editor = drawer.get_by_role("textbox", name="参考资料链接", exact=True)
    editor.fill("https://example.invalid/replacement")
    state["source_fail"] = True
    drawer.get_by_role("button", name="保存资料", exact=True).click()
    expect(
        drawer.get_by_text("资料已在其他窗口更新，草稿已保留", exact=True)
    ).to_be_visible()
    expect(editor).to_have_value("https://example.invalid/replacement")
    expect(
        drawer.get_by_role("button", name="移除新增附件 replacement.txt", exact=True)
    ).to_be_visible()
    assert state["source_writes"][0] == (
        dict(
            revision="a" * 64,
            retained_files="[]",
            content_urls="https://example.invalid/replacement",
        ),
        [("replacement.txt", b"REPLACEMENT")],
    )
    assert not state["writes"] and page.evaluate("outlineStreams.length") == 0
    drawer.get_by_role("button", name="保存资料", exact=True).focus()
    page.keyboard.press("Tab")
    assert drawer.evaluate("e=>e.contains(document.activeElement)")
    assert drawer.evaluate("e=>e.scrollWidth<=e.clientWidth")
    expect(
        drawer.get_by_role("button", name="保存资料", exact=True)
    ).to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    output = Path("artifacts/project-sources-20261022")
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(output / f"drawer-{width}.png"), full_page=True, animations="disabled"
    )
    state["source_fail"] = False
    drawer.get_by_role("button", name="保存资料", exact=True).click()
    expect(drawer).not_to_be_visible()
    expect(page.get_by_role("button", name="管理资料", exact=True)).to_be_focused()
    expect(
        page.get_by_text(
            "资料已更新，请重新生成大纲以应用修改。现有页面不会自动更新。", exact=True
        )
    ).to_be_visible()
    page.get_by_text("参考资料 · 1 个附件 · 1 个链接", exact=True).click()
    expect(page.locator(".todo-source-summary")).to_contain_text("replacement.txt")
    expect(page.locator(".todo-outline-summary")).to_contain_text(OUTLINE["title"])
    assert (
        not state["errors"]
        and not state["writes"]
        and page.evaluate("outlineStreams.length") == 0
    )


def test_read_failure_retry_and_dirty_close_preserve_materials(ui_page):
    page, load = ui_page
    state, _ = open_sources(page, load)
    state["source_read_fail"] = True
    page.get_by_role("button", name="管理资料", exact=True).click()
    drawer = page.get_by_role("dialog", name="管理参考资料", exact=True)
    expect(drawer.get_by_text("读取服务暂时不可用", exact=True)).to_be_visible()
    state["source_read_fail"] = False
    drawer.get_by_role("button", name="重试读取", exact=True).click()
    editor = drawer.get_by_role("textbox", name="参考资料链接", exact=True)
    expect(editor).to_have_value("https://example.invalid/old")
    editor.fill("")
    page.keyboard.press("Escape")
    confirmation = page.get_by_role("dialog", name="放弃未保存的资料修改？", exact=True)
    confirmation.get_by_role("button", name="继续编辑", exact=True).click()
    expect(editor).to_have_value("")
    drawer.get_by_role("button", name="取消", exact=True).click()
    page.get_by_role("button", name="放弃修改", exact=True).click()
    expect(drawer).not_to_be_visible()
    expect(page.get_by_role("button", name="管理资料", exact=True)).to_be_focused()
    assert not state["source_writes"] and not state["errors"]


def test_generation_lock_from_server_disables_material_save(ui_page):
    page, load = ui_page
    state, _ = open_sources(page, load)
    state["source_editable"] = False
    page.get_by_role("button", name="管理资料", exact=True).click()
    drawer = page.get_by_role("dialog", name="管理参考资料", exact=True)
    expect(
        drawer.get_by_role("textbox", name="参考资料链接", exact=True)
    ).to_be_disabled()
    expect(drawer.get_by_role("button", name="保存资料", exact=True)).to_be_disabled()
    expect(
        drawer.get_by_text("项目任务进行中，完成后可重新打开修改资料。", exact=True)
    ).to_be_visible()
    assert not state["source_writes"]


def test_unattended_run_disables_manage_button(ui_page):
    page, load = ui_page
    state, _ = open_sources(page, load, active=True)
    expect(page.get_by_role("button", name="管理资料", exact=True)).to_be_disabled()
    assert not state["source_reads"]
