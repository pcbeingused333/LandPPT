"""File and URL selections form one persistent, reviewable creation input."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_creation_workspace_ui import workspace
from test_antd_navigation_ui import open_navigation


def choose_source(page, path, label):
    if path == "/dashboard":
        page.locator(".composer-toolbar .ant-segmented").get_by_text(
            label, exact=True
        ).click()
    else:
        page.get_by_role("tab", name=label, exact=True).click()


@pytest.mark.parametrize("path", ["/dashboard", "/create"])
@pytest.mark.parametrize("width", [1440, 390, 320])
def test_mixed_submission_retry_and_clear_are_explicit_without_overflow(
    ui_page, path, width
):
    page, _ = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    state, calls = workspace(page, path)
    page.get_by_role("textbox", name="PPT 主题", exact=True).fill("混合资料")
    choose_source(page, path, "文件资料")
    page.locator("input[type=file]").set_input_files(
        [
            dict(name="notes.txt", mimeType="text/plain", buffer=b"LOCAL_ONE"),
            dict(
                name="data.md", mimeType="text/markdown", buffer=b"Year,Value\n2026,42"
            ),
        ]
    )
    choose_source(page, path, "网页链接")
    page.get_by_role("textbox", name="内容链接", exact=True).fill(
        "https://example.invalid/article\nhttps://example.invalid/report.pdf"
    )
    expect(
        page.get_by_text("附件与网页链接将合并用于生成大纲。", exact=True)
    ).to_be_visible()
    summary = page.get_by_role("status", name="已添加资料", exact=True)
    expect(summary).to_contain_text("2 个附件")
    expect(summary).to_contain_text("2 个链接")
    for _ in range(2):
        page.get_by_role("button", name="开始生成", exact=True).click()
        expect(page.get_by_text("保留草稿供重试", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    for write in calls["writes"]:
        fields, files = write[3]
        assert fields["content_source"] == "mixed"
        assert fields["content_urls"].splitlines() == [
            "https://example.invalid/article",
            "https://example.invalid/report.pdf",
        ]
        assert [item[1] for item in files] == ["notes.txt", "data.md"]
    page.get_by_role("button", name="清空链接", exact=True).click()
    expect(summary).not_to_contain_text("个链接")
    page.get_by_role("button", name="开始生成", exact=True).click()
    expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    fields, files = calls["writes"][-1][3]
    assert (
        fields["content_source"] == "file"
        and "content_urls" not in fields
        and len(files) == 2
    )
    for name in ["notes.txt", "data.md"]:
        page.get_by_role("button", name=f"移除附件 {name}", exact=True).click()
    expect(summary).to_have_count(0)
    page.get_by_role("button", name="开始生成", exact=True).click()
    expect(page.get_by_role("button", name="开始生成", exact=True)).to_be_enabled()
    fields, files = calls["writes"][-1][3]
    assert fields["content_source"] == "manual" and not files
    assert not state["errors"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_mixed_draft_survives_switching_between_shared_creation_views(ui_page):
    page, _ = ui_page
    state, calls = workspace(page)
    page.get_by_role("textbox", name="PPT 主题", exact=True).fill("持续创作")
    choose_source(page, "/dashboard", "文件资料")
    page.locator("input[type=file]").set_input_files(
        dict(name="notes.txt", mimeType="text/plain", buffer=b"LOCAL")
    )
    choose_source(page, "/dashboard", "网页链接")
    page.get_by_role("textbox", name="内容链接", exact=True).fill(
        "https://example.invalid/source"
    )
    open_navigation(page, "/projects")
    open_navigation(page, "/create")
    expect(page.get_by_role("textbox", name="内容链接", exact=True)).to_have_value(
        "https://example.invalid/source"
    )
    expect(
        page.get_by_role("button", name="移除附件 notes.txt", exact=True)
    ).to_be_visible()
    open_navigation(page, "/dashboard")
    page.get_by_role("button", name="开始生成", exact=True).click()
    expect(page.get_by_text("保留草稿供重试", exact=True)).to_be_visible()
    fields, files = calls["writes"][0][3]
    assert (
        fields["content_source"] == "mixed"
        and fields["content_urls"] == "https://example.invalid/source"
    )
    assert files == [("file_upload", "notes.txt", b"LOCAL")]
    assert not state["errors"]


@pytest.mark.parametrize("width", [1440, 320])
def test_planning_shows_saved_sources_without_disclosing_server_paths(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    project = dict(
        project_id="mixed",
        topic="mixed",
        scenario="general",
        title="Mixed sources",
        project_metadata={},
        confirmed_requirements={
            "content_source": "mixed",
            "uploaded_files": [
                {"filename": "notes.txt", "file_path": "/private/server/path.txt"}
            ],
            "source_urls": ["https://example.invalid/" + "long" * 60],
        },
        outline={
            "title": "Mixed sources",
            "slides": [
                {
                    "page_number": 1,
                    "title": "资料概述",
                    "content_points": ["文件与网页资料汇总"],
                }
            ],
            "metadata": {},
        },
        slides_data=[],
    )
    board = dict(
        task_id="mixed",
        title="Mixed sources",
        stages=[
            {"id": "requirements_confirmation", "status": "completed"},
            {"id": "outline_generation", "status": "completed"},
        ],
        current_stage_index=0,
        overall_progress=0,
    )
    load(
        "pages/project/todo_board.html",
        path="/projects/mixed/todo",
        project=project,
        todo_board=board,
    )
    page.get_by_text("参考资料 · 1 个附件 · 1 个链接", exact=True).click()
    expect(page.get_by_text("notes.txt", exact=True)).to_be_visible()
    link = page.locator(".todo-source-summary a")
    expect(link).to_have_attribute(
        "href", project["confirmed_requirements"]["source_urls"][0]
    )
    assert "private/server" not in page.locator("#antdData").text_content()
    assert json.loads(page.locator("#antdData").text_content())["sourceSummary"][
        "files"
    ] == ["notes.txt"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    output = Path("artifacts/mixed-sources-20261022")
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(output / f"planning-summary-{width}.png"),
        full_page=True,
        animations="disabled",
    )
