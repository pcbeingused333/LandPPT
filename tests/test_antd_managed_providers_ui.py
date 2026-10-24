"""Managed provider workflows against the built UI, with isolated API fixtures."""

from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_ui import settings

SIZES = [(1920, 1080), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
PROVIDERS = [
    dict(
        id=f"provider-{i}",
        provider=f"custom:provider-{i}",
        name=f"服务商 {i}",
        description="支持多种模型的 OpenAI 兼容服务。",
        logo_url="",
        base_url=f"https://relay{i}.example.com/v1",
        website_url=f"https://relay{i}.example.com",
        registration_url=f"https://relay{i}.example.com/register?ref=landppt",
        default_model="recommended-model",
        recommended_models=["recommended-model", "other-model"],
        model="saved-model",
        use_responses_api=False,
        sort_order=i * 10,
        is_active=True,
        has_api_key=True,
        configured=True,
        requires_confirmation=False,
    )
    for i in (1, 2)
]


def catalogue(page, *, admin=False, records=None):
    rows = deepcopy(records if records is not None else PROVIDERS)
    writes, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def api(route):
        path = urlsplit(route.request.url).path
        method = route.request.method
        if method == "GET":
            route.fulfill(json={"success": True, "providers": rows})
            return
        body = route.request.post_data_json if route.request.post_data else None
        writes.append((path, method, body))
        if path.endswith("/order"):
            rows[:] = [
                next(row for row in rows if row["id"] == item) for item in body["ids"]
            ]
        if path.endswith("/models"):
            route.fulfill(
                json={"success": True, "models": ["alpha", "beta", "saved-model"]}
            )
        elif path.endswith("/config") and method == "PUT":
            provider_id = path.split("/")[-2]
            next(row for row in rows if row["id"] == provider_id).update(
                configured=True,
                has_api_key=True,
                requires_confirmation=False,
                model=body["model"],
                enable_reasoning=body["enable_reasoning"],
                reasoning_effort=body["reasoning_effort"],
            )
            route.fulfill(json={"success": True})
        else:
            route.fulfill(json={"success": True})

    page.route(
        "**/" + ("admin/api/ai-providers" if admin else "api/managed-providers") + "**",
        api,
    )
    return rows, writes, errors


@pytest.mark.parametrize("width,height", SIZES)
def test_admin_catalogue_sorting_preview_and_layout(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    _, writes, errors = catalogue(page, admin=True)
    load("pages/admin/ai_providers.html", path="/admin/ai-providers")
    expect(page.get_by_role("heading", name="AI提供商管理", exact=True)).to_be_visible()
    expect(page.locator(".managed-provider-admin-row")).to_have_count(2)
    Path("artifacts/ai-providers").mkdir(parents=True, exist_ok=True)
    page.screenshot(path=f"artifacts/ai-providers/admin-{width}.png", full_page=True)
    page.get_by_role("button", name="下移 服务商 1", exact=True).click()
    expect(page.locator(".managed-provider-admin-row").first).to_contain_text(
        "服务商 2"
    )
    assert writes[0][2]["ids"] == ["provider-2", "provider-1"]
    page.get_by_role("button", name="预览", exact=True).first.click()
    dialog = page.get_by_role("dialog", name="提供商展示预览")
    expect(dialog.get_by_role("link", name="前往注册")).to_have_attribute(
        "href", "https://relay2.example.com/register?ref=landppt"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.get_by_role("button", name="关闭预览", exact=True).click()
    if width == 1440:
        rows = page.locator(".managed-provider-admin-row")
        rows.first.drag_to(rows.last)
        expect(rows.first).to_contain_text("服务商 1")
        assert writes[-1][2]["ids"] == ["provider-1", "provider-2"]
    assert not errors


@pytest.mark.parametrize("width,height", [(1440, 900), (320, 568)])
def test_admin_create_form_sends_metadata_without_credentials(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    _, writes, errors = catalogue(page, admin=True, records=[])
    load("pages/admin/ai_providers.html", path="/admin/ai-providers")
    page.get_by_role("button", name="添加提供商", exact=True).click()
    dialog = page.get_by_role("dialog", name="添加 AI 提供商")
    dialog.get_by_label("提供商名称", exact=True).fill("新服务商")
    dialog.get_by_label("API Base URL", exact=True).fill("https://new.example.com/v1")
    dialog.get_by_label("注册跳转链接", exact=True).fill(
        "https://new.example.com/signup?ref=lp"
    )
    dialog.get_by_label("推荐模型", exact=True).fill("model-a\nmodel-b")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    dialog.get_by_role("button", name="保存提供商", exact=True).click()
    expect(dialog).not_to_be_visible()
    body = writes[0][2]
    assert body["name"] == "新服务商" and body["recommended_models"] == [
        "model-a",
        "model-b",
    ]
    assert body["registration_url"].endswith("?ref=lp") and "api_key" not in body
    assert not errors


@pytest.mark.parametrize("width,height", SIZES)
def test_user_configuration_retains_key_and_lists_models(ui_page, width, height):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    _, writes, errors = catalogue(page)
    settings(page, load)
    expect(page.locator(".managed-provider-card")).to_have_count(2)
    Path("artifacts/ai-providers").mkdir(parents=True, exist_ok=True)
    page.screenshot(path=f"artifacts/ai-providers/settings-{width}.png", full_page=True)
    first = page.locator(".managed-provider-card").first
    expect(first.get_by_role("link", name="前往注册")).to_have_attribute(
        "target", "_blank"
    )
    first.get_by_role("button", name="配置使用", exact=True).click()
    dialog = page.get_by_role("dialog", name="配置 服务商 1")
    expect(dialog.get_by_label("API Key", exact=True)).to_have_value("")
    expect(dialog.get_by_label("API 地址", exact=True)).to_have_value(
        PROVIDERS[0]["base_url"]
    )
    dialog.get_by_role("button", name="获取提供商模型列表").click()
    expect(
        page.locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    ).to_have_text(["alpha", "beta", "saved-model"])
    page.locator(
        ".ant-select-dropdown:visible .ant-select-item-option-content"
    ).get_by_text("beta", exact=True).click()
    dialog.get_by_role("button", name="保存配置", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert writes[-1][2] == dict(
        api_key=None,
        model="beta",
        confirmed_base_url=PROVIDERS[0]["base_url"],
        enable_reasoning=False,
        reasoning_effort="medium",
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors


def test_changed_address_requires_explicit_confirmation(ui_page):
    page, load = ui_page
    rows = deepcopy(PROVIDERS[:1])
    rows[0].update(requires_confirmation=True, configured=False)
    _, writes, errors = catalogue(page, records=rows)
    settings(page, load)
    page.get_by_role("button", name="配置使用", exact=True).click()
    dialog = page.get_by_role("dialog", name="配置 服务商 1")
    dialog.get_by_role("button", name="保存配置", exact=True).click()
    expect(dialog.get_by_text("请先确认当前 API 地址", exact=True)).to_be_visible()
    assert not writes
    dialog.get_by_role("checkbox").check()
    dialog.get_by_role("button", name="保存配置", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert len(writes) == 1 and writes[0][2]["api_key"] is None
    assert not errors


@pytest.mark.parametrize("width,height", [(1440, 900), (320, 568)])
def test_reasoning_settings_are_used_for_probe_saved_and_restored(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    rows = deepcopy(PROVIDERS)
    rows[0].update(enable_reasoning=True, reasoning_effort="low")
    _, writes, errors = catalogue(page, records=rows)
    settings(page, load)
    first = page.locator(".managed-provider-card").first
    first.get_by_role("button", name="配置使用", exact=True).click()
    dialog = page.get_by_role("dialog", name="配置 服务商 1")
    switch = dialog.get_by_role("switch", name="启用思考", exact=True)
    effort = dialog.get_by_role("combobox", name="思考强度", exact=True)
    expect(switch).to_be_checked()
    switch.click()
    expect(effort).to_be_disabled()
    switch.click()
    effort.click()
    page.locator(".ant-select-dropdown:visible").get_by_text(
        "高（high）", exact=True
    ).click()
    dialog.get_by_role("button", name="测试连接", exact=True).click()
    expect(dialog.get_by_role("button", name="保存配置", exact=True)).to_be_enabled()
    assert writes[-1][0].endswith("/test")
    assert writes[-1][2]["enable_reasoning"] is True
    assert writes[-1][2]["reasoning_effort"] == "high"
    dialog.get_by_role("button", name="保存配置", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert writes[-1][0].endswith("/config")
    assert writes[-1][2]["reasoning_effort"] == "high"
    first.get_by_role("button", name="配置使用", exact=True).click()
    expect(switch).to_be_checked()
    expect(dialog.get_by_text("高（high）", exact=True)).to_be_visible()
    effort.scroll_into_view_if_needed()
    Path("artifacts/ai-providers").mkdir(parents=True, exist_ok=True)
    dialog.screenshot(path=f"artifacts/ai-providers/reasoning-{width}.png")
    switch.click()
    dialog.get_by_role("button", name="保存配置", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert writes[-1][2]["enable_reasoning"] is False
    page.locator(".managed-provider-card").nth(1).get_by_role(
        "button", name="配置使用", exact=True
    ).click()
    expect(
        page.get_by_role("dialog", name="配置 服务商 2").get_by_role(
            "switch", name="启用思考", exact=True
        )
    ).not_to_be_checked()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors


def test_managed_provider_is_available_in_task_selection(ui_page):
    page, load = ui_page
    _, writes, errors = catalogue(page)
    settings(page, load)
    page.locator(".ant-collapse-header").filter(has_text="模型任务配置").click()
    page.locator("#field-outline_model_provider").click()
    page.locator(".ant-select-dropdown:visible").get_by_text(
        "服务商 2", exact=True
    ).click()
    field = page.locator("#field-outline_model_name")
    field.locator(
        "xpath=ancestor::*[contains(@class, 'model-control')][1]"
    ).get_by_role("button", name="获取大纲生成模型列表", exact=True).click()
    expect(
        page.locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    ).to_have_text(["alpha", "beta", "saved-model"])
    assert writes[-1][:2] == ("/api/managed-providers/provider-2/models", "POST")
    assert not errors


def test_user_can_choose_a_managed_default_and_keep_failed_drafts(ui_page):
    page, load = ui_page
    _, writes, errors = catalogue(page)
    defaults = []

    def save_default(route):
        defaults.append(route.request.post_data_json)
        route.fulfill(json={"success": True})

    page.route("**/api/config/default-provider", save_default)
    settings(page, load)
    page.get_by_role("radio", name="设 服务商 1 为默认", exact=True).click()
    expect(
        page.get_by_role("radio", name="设 服务商 1 为默认", exact=True)
    ).to_be_checked()
    assert defaults == [{"provider": "custom:provider-1"}]
    page.locator(".managed-provider-card").first.get_by_role(
        "button", name="配置使用", exact=True
    ).click()
    dialog = page.get_by_role("dialog", name="配置 服务商 1")
    dialog.get_by_label("API Key", exact=True).fill("new-draft-key")
    dialog.get_by_label("模型", exact=True).fill("draft-model")
    page.route(
        "**/api/managed-providers/provider-1/test",
        lambda route: route.fulfill(status=502, json={"detail": "服务暂时不可用"}),
    )
    dialog.get_by_role("button", name="测试连接", exact=True).click()
    expect(dialog.get_by_text("服务暂时不可用", exact=True)).to_be_visible()
    expect(dialog.get_by_label("API Key", exact=True)).to_have_value("new-draft-key")
    expect(dialog.get_by_label("模型", exact=True)).to_have_value("draft-model")
    dialog.get_by_role("button", name="保存配置", exact=True).click()
    expect(dialog).not_to_be_visible()
    assert (
        writes[-1][2]["api_key"] == "new-draft-key"
        and writes[-1][2]["model"] == "draft-model"
    )
    assert not errors
