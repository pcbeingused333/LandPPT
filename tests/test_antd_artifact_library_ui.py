"""Stored-export catalogue UI on the existing image route; isolated APIs."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, detail_project, ui_page  # noqa: F401
from test_antd_admin_management_ui import select
from test_antd_images_ui import image_api

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


def library_setup(page, load, path="/image-gallery"):
    images = image_api(page)
    state = dict(
        reads=[],
        fail=False,
        malformed=False,
        hold=False,
        held=[],
        downloads=[],
        errors=[],
    )
    page.on("pageerror", lambda error: state["errors"].append(str(error)))
    files = []
    for index in range(61):
        kind = ["pdf", "pptx", "audio", "video"][index % 4]
        name = (
            "很长的文件名与内容检查" * 20
            if index == 0
            else (
                '<img src=x onerror="window.libraryInjected=true">'
                if index == 1
                else f"交付文件-{index:02d}"
            )
        )
        files.append(
            dict(
                id=f"file-{index:02d}",
                filename=name
                + {"pdf": ".pdf", "pptx": ".pptx", "audio": ".zip", "video": ".mp4"}[
                    kind
                ],
                category=kind,
                category_label={
                    "pdf": "PDF",
                    "pptx": "PPTX",
                    "audio": "讲解音频",
                    "video": "讲解视频",
                }[kind],
                file_size=None if index == 0 else index * 1024,
                created_at=1790000000 + index,
                project=dict(
                    id="ui-a" if index % 2 == 0 else "ui-b",
                    title="测试项目一" if index % 2 == 0 else "测试项目二",
                ),
                download_url=f"/api/artifacts/file-{index:02d}/download",
            )
        )
    state["files"] = files

    def endpoint(route):
        query = {
            key: value[0]
            for key, value in parse_qs(
                urlsplit(route.request.url).query, keep_blank_values=True
            ).items()
        }
        state["reads"].append(query)
        if state["hold"]:
            state["hold"] = False
            state["held"].append(route)
            return
        if state["fail"]:
            route.fulfill(status=503, json={"detail": "文件服务暂时不可用"})
            return
        if state["malformed"]:
            route.fulfill(
                json={"files": [], "pagination": {"total_count": -1, "current_page": 0}}
            )
            return
        found = list(files)
        if query.get("category"):
            found = [item for item in found if item["category"] == query["category"]]
        if query.get("project_id"):
            found = [
                item for item in found if item["project"]["id"] == query["project_id"]
            ]
        search = query.get("search", "").lower()
        found = [
            item
            for item in found
            if search in (item["filename"] + item["project"]["title"]).lower()
        ]
        if query.get("sort") == "largest":
            found.sort(key=lambda item: item["file_size"] or -1, reverse=True)
        else:
            found.sort(
                key=lambda item: item["created_at"],
                reverse=query.get("sort") != "oldest",
            )
        current = min(int(query["page"]), max(1, (len(found) + 19) // 20))
        project = (
            {"id": query["project_id"], "title": "测试项目一"}
            if query.get("project_id")
            else None
        )
        route.fulfill(
            json=dict(
                files=found[(current - 1) * 20 : current * 20],
                pagination=dict(
                    current_page=current, per_page=20, total_count=len(found)
                ),
                project=project,
            )
        )

    def download(route):
        state["downloads"].append(route.request.url)
        route.fulfill(
            body=b"STORED-FILE-FIXTURE",
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": "attachment; filename*=UTF-8''"
                + quote("已存储文件.pdf"),
            },
        )

    page.route("**/api/artifact-library*", endpoint)
    # Native URL downloads may be dispatched outside the page target.
    page.context.route("**/api/artifacts/*/download", download)
    load("pages/image/image_gallery.html", path=path)
    state["images"] = images
    return state


def files_tab(page):
    page.get_by_role("tab", name="导出文件", exact=True).click()
    expect(page.get_by_role("heading", name="导出文件", exact=True)).to_be_visible()
    return page.get_by_role("region", name="已保存的导出文件", exact=True)


@pytest.mark.parametrize("width,height", SIZES)
def test_catalogue_lazy_loads_and_stays_inside_viewport(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = library_setup(page, load)
    expect(page.locator(".image-card").first).to_be_visible()
    assert not state["reads"]
    region = files_tab(page)
    expect(region.locator(".ant-card")).to_have_count(20)
    expect(page.get_by_text("共 61 个文件", exact=True)).to_be_visible()
    select(page, "导出文件排序", "最早生成")
    expect(region.get_by_text("大小未知", exact=True)).to_be_visible()
    expect(
        region.get_by_text(state["files"][1]["filename"], exact=True)
    ).to_be_visible()
    assert not page.evaluate("window.libraryInjected")
    assert region.evaluate("e=>e.scrollWidth<=e.clientWidth")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    output = Path("artifacts/artifact-library-20261022")
    output.mkdir(parents=True, exist_ok=True)
    page.evaluate("scrollTo(0,0)")
    if width <= 390:
        expect(
            region.locator(".ant-card").first.locator("a[download]")
        ).to_be_in_viewport()
        for target in [
            page.get_by_role("button", name="刷新导出文件", exact=True),
            page.get_by_role("button", name="搜索导出文件", exact=True),
        ]:
            bounds = target.bounding_box()
            assert bounds["width"] >= 44 and bounds["height"] >= 44
    page.mouse.move(1, height - 2)
    page.screenshot(
        path=str(output / f"library-{width}x{height}.png"), animations="disabled"
    )
    page.get_by_role("tab", name="图片素材", exact=True).click()
    expect(page.locator(".image-card").first).to_be_visible()
    assert (
        not state["images"]["writes"] and not state["downloads"] and not state["errors"]
    )


def test_search_type_sort_pagination_and_empty_reset(ui_page):
    page, load = ui_page
    state = library_setup(page, load)
    region = files_tab(page)
    expect(region.locator(".ant-card")).to_have_count(20)
    page.locator(".artifact-library .ant-pagination-next").click()
    expect(region.get_by_text("交付文件-40.pdf", exact=True)).to_be_visible()
    assert state["reads"][-1]["page"] == "2"
    select(page, "导出文件类型", "讲解音频")
    expect(page.get_by_text("共 15 个文件", exact=True)).to_be_visible()
    assert state["reads"][-1]["page"] == "1"
    search = page.get_by_role("searchbox", name="搜索导出文件", exact=True)
    search.fill("交付文件-42")
    expect(region.locator(".ant-card")).to_have_count(1)
    expect(region.get_by_text("交付文件-42.zip", exact=True)).to_be_visible()
    search.fill("不存在的资料")
    expect(page.get_by_text("没有匹配的导出文件", exact=True)).to_be_visible()
    page.get_by_role("button", name="清除筛选", exact=True).click()
    expect(search).to_have_value("")
    expect(page.get_by_text("共 61 个文件", exact=True)).to_be_visible()
    assert (
        not state["downloads"] and not state["images"]["writes"] and not state["errors"]
    )


@pytest.mark.parametrize("malformed", [False, True])
def test_failed_or_invalid_list_keeps_filters_and_retries(ui_page, malformed):
    page, load = ui_page
    state = library_setup(page, load)
    files_tab(page)
    expect(page.get_by_text("共 61 个文件", exact=True)).to_be_visible()
    state["malformed" if malformed else "fail"] = True
    search = page.get_by_role("searchbox", name="搜索导出文件", exact=True)
    search.fill("交付文件-12")
    expect(page.get_by_text("导出文件加载失败", exact=True)).to_be_visible()
    expect(search).to_have_value("交付文件-12")
    state["fail"] = state["malformed"] = False
    page.get_by_role("button", name="重试", exact=True).click()
    expect(page.get_by_text("共 1 个文件", exact=True)).to_be_visible()
    assert state["reads"][-1]["search"] == "交付文件-12"
    assert not state["downloads"] and not state["errors"]


def test_project_deep_link_and_removal_update_scope_without_image_writes(ui_page):
    page, load = ui_page
    state = library_setup(page, load, path="/image-gallery?tab=exports&project=ui-a")
    expect(page.get_by_role("heading", name="导出文件", exact=True)).to_be_visible()
    expect(page.get_by_text("共 31 个文件", exact=True)).to_be_visible()
    assert state["reads"][-1]["project_id"] == "ui-a"
    page.get_by_role("button", name="查看所有项目文件", exact=True).click()
    expect(page.get_by_text("共 61 个文件", exact=True)).to_be_visible()
    assert "project_id" not in state["reads"][-1]
    assert "project=" not in page.url and "tab=exports" in page.url
    assert not state["images"]["writes"] and not state["errors"]


def test_native_download_retains_filename_and_does_not_navigate_or_buffer_in_app(
    ui_page,
):
    page, load = ui_page
    state = library_setup(page, load)
    # Native downloads can bypass Playwright's page/context interception. Serve
    # one real local response so both filename and completed bytes are verified.
    requests = []

    class DownloadHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            assert self.path == "/api/artifacts/file-60/download"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''" + quote("已存储文件.pdf"),
            )
            self.end_headers()
            self.wfile.write(b"STORED-FILE-FIXTURE")

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), DownloadHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page.context.unroute("**/api/artifacts/*/download")
        page.context.route(
            "**/api/artifacts/*/download", lambda route: route.continue_()
        )
        page.goto(f"http://127.0.0.1:{server.server_port}/image-gallery")
        region = files_tab(page)
        link = region.get_by_role("link", name="下载 交付文件-60.pdf", exact=True)
        expect(link).to_have_attribute("download", "")
        before = page.url
        with page.expect_download() as event:
            link.click()
        assert event.value.suggested_filename == "已存储文件.pdf"
        assert Path(event.value.path()).read_bytes() == b"STORED-FILE-FIXTURE"
        assert page.url == before and requests == ["/api/artifacts/file-60/download"]
        assert not state["images"]["writes"] and not state["errors"]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_tab_switch_aborts_pending_read_and_preserves_filter(ui_page):
    page, load = ui_page
    state = library_setup(page, load)
    files_tab(page)
    expect(page.get_by_text("共 61 个文件", exact=True)).to_be_visible()
    state["hold"] = True
    search = page.get_by_role("searchbox", name="搜索导出文件", exact=True)
    search.fill("交付文件-12")
    expect(page.get_by_text("正在读取导出文件…", exact=True)).to_be_visible()
    assert len(state["held"]) == 1
    page.get_by_role("tab", name="图片素材", exact=True).click()
    files_tab(page)
    expect(page.get_by_text("共 1 个文件", exact=True)).to_be_visible()
    expect(search).to_have_value("交付文件-12")
    assert not state["errors"] and not state["images"]["writes"]


def test_project_menu_file_link_does_not_open_delete_confirmation(
    ui_page, detail_project
):
    page, load = ui_page
    image_api(page)
    load(
        "pages/project/project_detail.html",
        path="/projects/ui-detail",
        project=detail_project,
    )
    page.get_by_role("button", name="项目更多操作", exact=True).click()
    link = page.get_by_role("link", name="查看导出文件", exact=True)
    expect(link).to_have_attribute(
        "href", "/image-gallery?tab=exports&project=ui-detail"
    )
    link.evaluate("node=>node.addEventListener('click',event=>event.preventDefault())")
    link.click()
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_file_scope_help_is_available_without_fetching_or_writing(ui_page):
    page, load = ui_page
    state = library_setup(page, load)
    files_tab(page)
    expect(page.get_by_text("共 61 个文件", exact=True)).to_be_visible()
    before = len(state["reads"])
    page.get_by_role("button", name="文件范围", exact=True).click()
    expect(
        page.get_by_text(
            "客户端 PPTX 和 HTML 文件包不会自动入库，请在浏览器下载目录中查找。",
            exact=True,
        )
    ).to_be_visible()
    page.get_by_role("button", name="文件范围", exact=True).click()
    assert len(state["reads"]) == before
    assert not state["images"]["writes"] and not state["errors"]
