"""Image UI regressions using actual templates/build and isolated image APIs."""

import base64
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_admin_management_ui import select

SIZES = [(1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400"><rect width="640" height="400" fill="#e8e8eb"/><path d="M0 400L240 100L420 320L520 180L640 400" fill="#555"/></svg>'
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jgZkAAAAASUVORK5CYII="
)
IMAGES = [
    dict(
        image_id=f"image-{index}",
        title=title,
        filename=f"asset-{index}.png",
        description="可重复使用的图片素材",
        tags="素材, 示例",
        category="ai_generated",
        source_type="ai_generated",
        file_size=35840,
        width=640,
        height=400,
        format="png",
        created_at=1790870400,
        access_count=2,
    )
    for index, title in enumerate(
        [
            "结构化网络示意",
            "图片素材标题与布局检查" * 15,
            '<img src=x onerror="window.injected=true">',
        ]
    )
]


def image_api(page):
    state = dict(
        reads=[],
        writes=[],
        images=IMAGES.copy(),
        total=41,
        failed_ids=[],
        available=["dalle", "openai_image", "gemini"],
        status="ok",
    )

    def api(route):
        request = route.request
        path = urlsplit(request.url).path
        if request.method == "GET":
            state["reads"].append(request.url)
        else:
            body = (
                request.post_data_json
                if "application/json" in request.headers.get("content-type", "")
                else None
            )
            state["writes"].append((path, request.method, body))
        if "/thumbnail/" in path or "/view/" in path:
            route.fulfill(body=SVG, content_type="image/svg+xml")
            return
        if "/download/" in path or path.endswith("batch-download"):
            route.fulfill(
                body=PNG,
                content_type=(
                    "application/zip"
                    if path.endswith("batch-download")
                    else "image/png"
                ),
                headers={
                    "Content-Disposition": (
                        "attachment; filename*=UTF-8''%E7%B4%A0%E6%9D%90.png"
                        if "/download/" in path
                        else 'attachment; filename="images.zip"'
                    )
                },
            )
            return
        if path.endswith("/list"):
            result = dict(
                success=True,
                images=state["images"],
                pagination=dict(total_count=state["total"]),
            )
        elif "/detail/" in path:
            result = dict(
                success=True,
                image=next(
                    image
                    for image in IMAGES
                    if image["image_id"] == path.rsplit("/", 1)[-1]
                ),
            )
        elif path.endswith("/status"):
            result = dict(
                status=state["status"], available_providers=state["available"]
            )
        elif path.endswith("/generate"):
            result = dict(
                success=True,
                image_path="http://ui.test/api/image/view/generated?width=1792px&height=1024px",
            )
        elif path.endswith("/update"):
            result = dict(success=True, image=request.post_data_json)
        elif path.endswith("batch-delete"):
            result = dict(
                success=True,
                failed_ids=state["failed_ids"],
                deleted_count=1,
                failed_count=len(state["failed_ids"]),
            )
        else:
            result = dict(success=True)
        route.fulfill(json=result)

    page.route("**/api/image/**", api)
    return state


def gallery(page, load):
    state = image_api(page)
    load("pages/image/image_gallery.html", path="/image-gallery")
    page.locator(".image-card").first.wait_for()
    return state


def generation(page, load):
    state = image_api(page)
    load("pages/image/image_generation_test.html", path="/image-generation-test")
    page.get_by_role("heading", name="AI 图片生成", exact=True).wait_for()
    return state


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize(
    "scene", ["gallery", "batch", "upload", "detail", "edit", "generation"]
)
def test_image_pages_and_modal_actions_fit_viewports(ui_page, width, height, scene):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = generation(page, load) if scene == "generation" else gallery(page, load)
    if scene == "batch":
        page.get_by_role("button", name="批量选择", exact=True).click()
        page.get_by_role("button", name="选择本页").click()
    if scene == "upload":
        page.get_by_role("button", name="上传图片", exact=True).click()
    if scene in {"detail", "edit"}:
        page.get_by_role("button", name="查看图片：结构化网络示意", exact=True).click()
        page.get_by_role("button", name="编辑信息", exact=True).wait_for()
        if scene == "edit":
            page.get_by_role("button", name="编辑信息", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not state["writes"]
    assert not errors
    assert not page.evaluate("!!window.injected")
    if scene in {"upload", "detail", "edit"}:
        dialog = page.get_by_role("dialog")
        box = dialog.locator(".ant-modal-container").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
        for button in dialog.locator(".ant-modal-footer button").all():
            bounds = button.bounding_box()
            assert bounds["y"] + bounds["height"] <= height
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate("!!document.activeElement.closest('.ant-modal')")
        page.keyboard.press("Escape")
        assert not dialog.is_visible()


def test_gallery_filters_keep_server_query_and_pagination(ui_page):
    page, load = ui_page
    state = gallery(page, load)
    select(page, "图片分类", "本地上传")
    page.get_by_role("searchbox", name="搜索图片").fill("素材 & UI")
    select(page, "图片排序", "文件从小到大")
    page.wait_for_timeout(250)
    page.locator(".ant-pagination-item-2").click()
    page.wait_for_timeout(50)
    params = parse_qs(urlsplit(state["reads"][-1]).query)
    assert params == dict(
        page=["2"],
        per_page=["20"],
        category=["local_storage"],
        search=["素材 & UI"],
        sort=["size_asc"],
    )
    assert not state["writes"]


def test_failed_list_retry_retains_requested_page_and_visible_cards(ui_page):
    page, load = ui_page
    gallery(page, load)
    calls = []

    def fail_once(route):
        calls.append(route.request.url)
        route.fulfill(
            status=503 if len(calls) == 1 else 200,
            json=(
                dict(detail="暂时不可用")
                if len(calls) == 1
                else dict(success=True, images=IMAGES, pagination=dict(total_count=41))
            ),
        )

    page.route("**/api/image/gallery/list?**", fail_once)
    page.locator(".ant-pagination-item-2").click()
    page.get_by_text("图库加载失败", exact=True).wait_for()
    assert page.locator(".image-card").count() == 3
    page.get_by_role("button", name="重试", exact=True).click()
    page.wait_for_timeout(50)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert parse_qs(urlsplit(calls[1]).query)["page"] == ["2"]
    assert not page.get_by_text("图库加载失败", exact=True).is_visible()


def test_partial_batch_delete_keeps_failed_selection_for_retry(ui_page):
    page, load = ui_page
    state = gallery(page, load)
    state["failed_ids"] = ["image-1"]
    page.get_by_role("button", name="批量选择", exact=True).click()
    page.get_by_role("checkbox", name="选择 结构化网络示意", exact=True).check()
    page.get_by_role("checkbox", name="选择 " + IMAGES[1]["title"], exact=True).check()
    page.get_by_role("button", name="删除选中", exact=True).click()
    page.get_by_role("dialog").get_by_role("button", name="确认", exact=True).click()
    page.get_by_text("已选择 1 张", exact=True).wait_for()
    assert state["writes"] == [
        (
            "/api/image/gallery/batch-delete",
            "POST",
            dict(image_ids=["image-0", "image-1"]),
        )
    ]
    assert page.get_by_role(
        "checkbox", name="选择 " + IMAGES[1]["title"], exact=True
    ).is_checked()


@pytest.mark.parametrize("cancel_stage", [1, 2, 0])
def test_clear_gallery_requires_both_confirmations(ui_page, cancel_stage):
    page, load = ui_page
    state = gallery(page, load)
    page.get_by_role("button", name="批量选择", exact=True).click()
    page.get_by_role("button", name="清空我的图库", exact=True).click()
    if cancel_stage == 1:
        page.get_by_role("dialog").get_by_role(
            "button", name="取消", exact=True
        ).click()
    else:
        page.get_by_role("dialog").get_by_role(
            "button", name="继续", exact=True
        ).click()
        dialog = page.get_by_role("dialog", name="再次确认清空图库", exact=True)
        dialog.get_by_role(
            "button", name="取消" if cancel_stage == 2 else "确认清空", exact=True
        ).click()
    page.wait_for_timeout(50)
    assert state["writes"] == (
        [] if cancel_stage else [("/api/image/gallery/clear-all", "POST", None)]
    )


def test_image_edit_failure_keeps_draft_and_retries_exact_payload(ui_page):
    page, load = ui_page
    gallery(page, load)
    page.get_by_role("button", name="查看图片：结构化网络示意", exact=True).click()
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("标题", exact=True).fill(" 改好的标题 ")
    page.get_by_label("描述", exact=True).fill(" 描述 ")
    page.get_by_label("标签", exact=True).fill(" a, b ")
    select(page, "来源分类", "本地上传")
    writes = []

    def update(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            status=500 if len(writes) == 1 else 200,
            json=(
                dict(detail="保存失败")
                if len(writes) == 1
                else dict(success=True, image=writes[-1])
            ),
        )

    page.route("**/api/image/image-0/update", update)
    page.get_by_role("button", name="保存信息", exact=True).click()
    page.get_by_text("保存失败", exact=True).wait_for()
    assert page.get_by_label("标题", exact=True).input_value() == " 改好的标题 "
    page.get_by_role("button", name="保存信息", exact=True).click()
    page.get_by_role("dialog", name="图片详情", exact=True).wait_for()
    assert page.get_by_role("dialog").get_by_text("本地上传", exact=True).is_visible()
    assert (
        writes
        == [
            dict(
                title="改好的标题",
                description="描述",
                tags="a, b",
                category="local_storage",
            )
        ]
        * 2
    )


def test_partial_upload_retries_only_failed_file_with_same_metadata(ui_page):
    page, load = ui_page
    gallery(page, load)
    page.get_by_role("button", name="上传图片", exact=True).click()
    page.locator('input[type="file"]').set_input_files(
        [
            dict(name="one.png", mimeType="image/png", buffer=PNG),
            dict(name="two.png", mimeType="image/png", buffer=PNG),
        ]
    )
    page.get_by_label("标题", exact=True).fill("共用标题")
    page.get_by_label("描述", exact=True).fill("测试说明")
    page.get_by_label("标签", exact=True).fill("a, b")
    writes = []

    def upload(route):
        writes.append(route.request.post_data_buffer.decode("latin1"))
        route.fulfill(
            status=500 if len(writes) == 2 else 200,
            json=dict(detail="服务繁忙") if len(writes) == 2 else dict(success=True),
        )

    page.route("**/api/image/upload", upload)
    page.get_by_role("button", name="开始上传", exact=True).click()
    page.get_by_text("部分文件未上传", exact=True).wait_for()
    assert page.locator(".ant-upload-list-item").count() == 1
    assert page.get_by_label("标题", exact=True).input_value() == "共用标题"
    page.get_by_role("button", name="重试未完成文件", exact=True).click()
    page.get_by_role("dialog").wait_for(state="hidden")
    assert len(writes) == 3
    assert 'filename="one.png"' in writes[0]
    assert 'filename="two.png"' in writes[1] and 'filename="two.png"' in writes[2]
    for body in writes:
        for name in ["file", "title", "description", "tags", "category"]:
            assert f'name="{name}"' in body
        assert "business" in body
        for value in ["共用标题", "测试说明", "a, b"]:
            assert value.encode("utf-8").decode("latin1") in body


def test_invalid_upload_file_is_rejected_without_write(ui_page):
    page, load = ui_page
    state = gallery(page, load)
    page.get_by_role("button", name="上传图片", exact=True).click()
    page.locator('input[type="file"]').set_input_files(
        dict(name="script.txt", mimeType="text/plain", buffer=b"invalid")
    )
    page.get_by_text(
        "script.txt：请选择 JPG、PNG、WebP 或 GIF 图片", exact=True
    ).wait_for()
    assert page.get_by_role("button", name="开始上传", exact=True).is_disabled()
    assert not state["writes"]


def test_download_uses_attachment_filename_and_zip_payload(ui_page):
    page, load = ui_page
    state = gallery(page, load)
    with page.expect_download() as downloaded:
        page.locator(".image-card").first.get_by_role(
            "button", name="下载", exact=True
        ).click()
    assert downloaded.value.suggested_filename == "素材.png"
    page.get_by_role("button", name="批量选择", exact=True).click()
    page.get_by_role("button", name="选择本页", exact=True).click()
    with page.expect_download() as downloaded:
        page.get_by_role("button", name="下载选中", exact=True).click()
    assert downloaded.value.suggested_filename == "images.zip"
    assert state["writes"][-1] == (
        "/api/image/gallery/batch-download",
        "POST",
        dict(image_ids=[image["image_id"] for image in IMAGES]),
    )


@pytest.mark.parametrize(
    "provider,quality",
    [
        ("DALL-E 3", "standard"),
        ("OpenAI 图片", "standard"),
        ("Gemini", None),
        ("SiliconFlow", "standard"),
        ("Stable Diffusion", "standard"),
    ],
)
def test_generate_retains_request_contract_and_image_dimensions(
    ui_page, provider, quality
):
    page, load = ui_page
    state = generation(page, load)
    page.get_by_label("提示词", exact=True).fill("画一张简洁的流程图")
    select(page, "AI 提供者", provider)
    page.get_by_role("button", name="生成图片", exact=True).click()
    page.get_by_text("生成成功", exact=True).wait_for()
    values = state["writes"][0][2]
    assert values == dict(
        prompt="画一张简洁的流程图",
        provider={
            "DALL-E 3": "dalle",
            "OpenAI 图片": "openai_image",
            "Gemini": "gemini",
            "SiliconFlow": "siliconflow",
            "Stable Diffusion": "stable_diffusion",
        }[provider],
        width=1792,
        height=1024,
        quality=quality,
    )
    assert (
        page.locator(".image-result img").get_attribute("src")
        == "/api/image/view/generated?width=1792px&height=1024px"
    )
    assert (
        len(json.loads(page.evaluate("localStorage.getItem('imageGenerationHistory')")))
        == 1
    )


def test_generation_validation_failure_and_retry_keep_user_input(ui_page):
    page, load = ui_page
    generation(page, load)
    page.get_by_role("button", name="生成图片", exact=True).click()
    page.get_by_text("请输入提示词", exact=True).wait_for()
    page.get_by_label("提示词", exact=True).fill(
        "<script>window.injected=true</script>"
    )
    select(page, "AI 提供者", "OpenAI 图片")
    writes = []

    def generate(route):
        writes.append(route.request.post_data_json)
        route.fulfill(
            status=502 if len(writes) == 1 else 200,
            json=(
                dict(detail="提供者暂时不可用")
                if len(writes) == 1
                else dict(success=True, image_path="/api/image/view/generated")
            ),
        )

    page.route("**/api/image/generate", generate)
    page.get_by_role("button", name="生成图片", exact=True).click()
    page.get_by_text("提供者暂时不可用", exact=True).wait_for()
    assert (
        page.get_by_label("提示词", exact=True).input_value()
        == "<script>window.injected=true</script>"
    )
    page.get_by_role("button", name="生成图片", exact=True).click()
    page.get_by_text("生成成功", exact=True).wait_for()
    assert writes[0] == writes[1]
    assert not page.evaluate("!!window.injected")


def test_historical_result_restores_prompt_and_clear_never_deletes_images(ui_page):
    page, load = ui_page
    item = dict(
        id=1,
        imageUrl="/api/image/view/old?width=640px",
        prompt="之前的图片",
        provider="dalle",
        timestamp="2026/10/11 10:00",
    )
    page.add_init_script(
        "localStorage.setItem('imageGenerationHistory', "
        + json.dumps(json.dumps([item]))
        + ");"
    )
    state = generation(page, load)
    page.get_by_role("button", name="查看历史：之前的图片", exact=True).click()
    assert page.get_by_label("提示词", exact=True).input_value() == "之前的图片"
    assert page.locator(".image-result img").get_attribute("src") == item["imageUrl"]
    page.get_by_role("button", name="清空历史", exact=True).click()
    page.get_by_role("dialog").get_by_role("button", name="确认", exact=True).click()
    page.get_by_text("暂无生成记录", exact=True).wait_for()
    assert page.evaluate("localStorage.getItem('imageGenerationHistory')") is None
    assert not state["writes"]


@pytest.mark.parametrize(
    "history",
    [
        "invalid JSON",
        '{"id":1}',
        '[null,{"id":1,"imageUrl":"javascript:alert(1)","prompt":"x","provider":"dalle","timestamp":"today"}]',
    ],
)
def test_malformed_history_does_not_crash_or_render_unsafe_urls(ui_page, history):
    page, load = ui_page
    page.add_init_script(
        "localStorage.setItem('imageGenerationHistory', " + json.dumps(history) + ");"
    )
    generation(page, load)
    assert page.get_by_text("暂无生成记录", exact=True).is_visible()
    assert page.get_by_role("button", name="生成图片", exact=True).is_enabled()


def test_provider_status_failure_can_retry_without_generating(ui_page):
    page, load = ui_page
    state = image_api(page)
    count = []

    def status(route):
        count.append(1)
        route.fulfill(
            status=503 if len(count) == 1 else 200,
            json=(
                dict(detail="状态服务不可用")
                if len(count) == 1
                else dict(status="disabled", available_providers=[])
            ),
        )

    page.route("**/api/image/status", status)
    load("pages/image/image_generation_test.html", path="/image-generation-test")
    page.get_by_text("状态加载失败", exact=True).wait_for()
    page.get_by_role("button", name="重试", exact=True).click()
    page.get_by_text("图片服务未启用，请在系统配置中检查设置。", exact=True).wait_for()
    assert len(count) == 2
    assert not state["writes"]


def test_generation_waits_without_fake_percent_or_duplicate_requests(ui_page):
    page, load = ui_page
    page.add_init_script(
        """const originalFetch=window.fetch; window.generationRequests=0;
        window.fetch=(url,...args)=>String(url)==='/api/image/generate'
          ? (window.generationRequests++, new Promise(resolve=>{window.finishGeneration=()=>originalFetch(url,...args).then(resolve)}))
          : originalFetch(url,...args);"""
    )
    generation(page, load)
    page.get_by_label("提示词", exact=True).fill("简洁的示意图")
    select(page, "AI 提供者", "DALL-E 3")
    page.get_by_role("button", name="生成图片", exact=True).click()
    page.get_by_text("正在生成，已用时 0 秒…", exact=True).wait_for()
    assert page.get_by_role("button", name="生成图片", exact=True).is_disabled()
    assert page.get_by_label("提示词", exact=True).is_disabled()
    page.locator(".image-generation-page form").evaluate(
        "form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))"
    )
    page.wait_for_timeout(50)
    assert page.evaluate("window.generationRequests") == 1
    assert page.get_by_role("progressbar").count() == 0
    page.evaluate("window.finishGeneration()")
    page.get_by_text("生成成功", exact=True).wait_for()
    assert page.get_by_role("button", name="生成图片", exact=True).is_enabled()


@pytest.mark.parametrize("path", ["", "javascript:alert(1)"])
def test_invalid_generation_result_keeps_retry_available(ui_page, path):
    page, load = ui_page
    generation(page, load)
    page.route(
        "**/api/image/generate",
        lambda route: route.fulfill(json=dict(success=True, image_path=path)),
    )
    page.get_by_label("提示词", exact=True).fill("简洁的示意图")
    select(page, "AI 提供者", "DALL-E 3")
    page.get_by_role("button", name="生成图片", exact=True).click()
    page.get_by_text("生成结果缺少有效的图片链接，请重试。", exact=True).wait_for()
    assert page.get_by_role("button", name="生成图片", exact=True).is_enabled()
    assert not page.locator(".image-result img").count()


def test_failed_detail_read_blocks_edit_and_can_retry(ui_page):
    page, load = ui_page
    gallery(page, load)
    reads = []

    def detail(route):
        reads.append(route.request.url)
        route.fulfill(
            status=503 if len(reads) == 1 else 200,
            json=(
                dict(detail="详情暂时不可用")
                if len(reads) == 1
                else dict(success=True, image={**IMAGES[0], "access_count": 0})
            ),
        )

    page.route("**/api/image/detail/image-0", detail)
    page.get_by_role("button", name="查看图片：结构化网络示意", exact=True).click()
    page.get_by_text("详情加载失败", exact=True).wait_for()
    assert page.get_by_role("button", name="编辑信息", exact=True).count() == 0
    page.get_by_role("button", name="重试", exact=True).click()
    page.get_by_role("button", name="编辑信息", exact=True).wait_for()
    assert len(reads) == 2
    assert page.get_by_role("dialog").get_by_text("0", exact=True).is_visible()


def test_delete_failure_keeps_confirmation_and_retry_payload(ui_page):
    page, load = ui_page
    gallery(page, load)
    writes = []

    def remove(route):
        writes.append(route.request.method)
        route.fulfill(
            status=503 if len(writes) == 1 else 200,
            json=(
                dict(detail="删除暂时不可用")
                if len(writes) == 1
                else dict(success=True)
            ),
        )

    page.route("**/api/image/delete/image-0", remove)
    page.get_by_role("button", name="删除 结构化网络示意", exact=True).click()
    dialog = page.get_by_role("dialog", name="删除图片", exact=True)
    dialog.get_by_role("button", name="确认", exact=True).click()
    page.get_by_text("删除暂时不可用", exact=True).wait_for()
    assert dialog.is_visible()
    dialog.get_by_role("button", name="确认", exact=True).click()
    dialog.wait_for(state="hidden")
    assert writes == ["DELETE", "DELETE"]


def test_batch_shortcuts_select_current_page_and_confirm_delete(ui_page):
    page, load = ui_page
    state = gallery(page, load)
    trigger = page.get_by_role("button", name="批量选择", exact=True)
    trigger.click()
    page.keyboard.press("Control+a")
    page.get_by_text("已选择 3 张", exact=True).wait_for()
    page.keyboard.press("Delete")
    dialog = page.get_by_role("dialog", name="删除 3 张图片", exact=True)
    dialog.get_by_role("button", name="取消", exact=True).click()
    assert not state["writes"]
    assert trigger.evaluate("element=>element===document.activeElement")
    page.get_by_role("button", name="清除选择", exact=True).click()
    field = page.get_by_role("searchbox", name="搜索图片")
    field.fill("素材")
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    assert page.get_by_text("已选择 0 张", exact=True).is_visible()
    assert not state["writes"]
