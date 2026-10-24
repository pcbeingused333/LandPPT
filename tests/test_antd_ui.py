"""Regressions against built Ant Design assets and the real Jinja field catalogue."""

import json
from types import SimpleNamespace

import pytest

from test_app_ui import browser, ui_page  # noqa: F401


def settings(page, load, **values):
    load("pages/settings/ai_config.html", path="/ai-config", **values)
    page.get_by_role("heading", name="系统配置管理").wait_for()


def test_antd_settings_retains_every_authorized_field(ui_page):
    page, load = ui_page
    settings(page, load)
    catalogue = page.evaluate(
        """() => [...document.querySelector('#settingsBlueprint').content
        .querySelectorAll('[name]')].filter(e=>!['radio','range'].includes(e.type))
        .map(e=>e.name)"""
    )
    for tab in page.get_by_role("tab").all():
        tab.click()
        if tab.inner_text() == "AI 提供者":
            for provider in ["LandPPT", "Anthropic Claude", "Google Gemini"]:
                page.locator(".ant-collapse-header").filter(
                    has_text=provider
                ).first.click()
            page.locator(".ant-collapse-header").filter(has_text="模型任务配置").click()
        if tab.inner_text() == "图片服务":
            for name in [
                "enable_image_service",
                "enable_local_images",
                "enable_network_search",
                "enable_ai_generation",
            ]:
                control = page.locator("#field-" + name)
                if control.get_attribute("aria-checked") != "true":
                    control.click()
    for name in set(catalogue):
        assert page.locator("#field-" + name).count() >= 1, name


def test_antd_dashboard_serializes_only_public_user_fields(ui_page):
    page, load = ui_page
    load(
        "pages/project/project_dashboard.html",
        user=SimpleNamespace(
            username="production-user", is_admin=True, secret="must-not-render"
        ),
    )
    page.get_by_role("heading", name="首页").wait_for()
    data = json.loads(page.locator("#antdData").text_content())
    assert data["user"] == {"username": "production-user", "is_admin": True}
    assert "must-not-render" not in page.content()


def test_antd_provider_preserves_payload_and_reasoning_linkage(ui_page):
    page, load = ui_page
    writes = []

    def capture(route):
        if route.request.method == "POST":
            writes.append(route.request.post_data_json)
        route.fulfill(json={"success": True, "config": {}})

    page.route("**/api/config/ai_providers", capture)
    settings(page, load)
    page.locator("#field-openai_api_key").fill("fixture-key")
    page.locator("#field-openai_model").fill("fixture-model")
    page.locator("#field-openai_enable_reasoning").click()
    assert page.locator("#field-openai_reasoning_effort").is_enabled()
    page.get_by_role("button", name="保存 OpenAI", exact=True).click()
    page.wait_for_timeout(100)
    assert len(writes) == 1
    assert writes[0] == {
        "config": {
            "openai_api_key": "fixture-key",
            "openai_model": "fixture-model",
            "openai_use_responses_api": False,
            "openai_enable_reasoning": True,
            "openai_reasoning_effort": "medium",
        }
    }


def test_antd_save_failure_keeps_values_and_allows_retry(ui_page):
    page, load = ui_page
    attempts = []

    def capture(route):
        attempts.append(route.request.post_data_json)
        route.fulfill(
            status=503 if len(attempts) == 1 else 200,
            json={"detail": "暂时不可用"} if len(attempts) == 1 else {"success": True},
        )

    page.route("**/api/config/generation_params", capture)
    settings(page, load)
    page.get_by_role("tab", name="生成参数", exact=True).click()
    field = page.locator("#field-temperature")
    field.fill("1.2")
    save = page.get_by_role("button", name="保存生成参数", exact=True)
    save.click()
    page.get_by_role("alert").filter(has_text="暂时不可用").wait_for()
    assert field.input_value() == "1.2"
    assert save.is_enabled()
    save.click()
    page.wait_for_timeout(100)
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert attempts[1]["config"]["temperature"] == "1.2"


def test_antd_save_ignores_repeated_clicks(ui_page):
    page, load = ui_page
    writes = []

    def capture(route):
        writes.append(route.request.post_data_json)
        route.fulfill(json={"success": True})

    page.route("**/api/config/generation_params", capture)
    settings(page, load)
    page.get_by_role("tab", name="生成参数", exact=True).click()
    page.get_by_role("button", name="保存生成参数", exact=True).evaluate(
        "button => { button.click(); button.click(); }"
    )
    page.wait_for_timeout(100)
    assert len(writes) == 1


def test_antd_pollinations_list_keeps_only_image_models(ui_page):
    page, load = ui_page
    page.route(
        "https://gen.pollinations.ai/image/models",
        lambda route: route.fulfill(
            json=[
                {"name": "text-model", "output_modalities": ["text"]},
                {"name": "image-model", "output_modalities": ["image"]},
            ]
        ),
    )
    settings(
        page,
        load,
        current_config={"enable_image_service": True, "enable_ai_generation": True},
    )
    page.get_by_role("tab", name="图片服务", exact=True).click()
    page.locator(".image-credentials-collapse .ant-collapse-header").filter(
        has_text="Pollinations"
    ).click()
    page.get_by_role("button", name="获取模型", exact=True).click()
    page.get_by_text("已获取 1 个模型", exact=True).wait_for()
    page.locator("#field-pollinations_model").click()
    page.locator(".ant-select-item-option-content").filter(
        has_text="image-model"
    ).wait_for()
    assert (
        page.locator(".ant-select-item-option-content")
        .filter(has_text="text-model")
        .count()
        == 0
    )


def test_antd_jev_empty_key_keeps_saved_secret_and_test_does_not_save(ui_page):
    page, load = ui_page
    writes = []

    def capture(route):
        if route.request.method != "GET":
            writes.append(
                (route.request.method, route.request.url, route.request.post_data_json)
            )
        route.fulfill(
            json={
                "configured": True,
                "enabled": True,
                "protocol": "jev",
                "endpoint_url": "https://api.example.invalid/v1/systemone",
                "model": "jev-example",
                "timeout": 30,
                "retries": 2,
                "concurrency": 1,
                "elapsed_ms": 40,
            }
        )

    page.route("**/api/global-master-templates/packages/settings**", capture)
    settings(page, load)
    page.get_by_role("tab", name="决策模型配置", exact=True).click()
    panel = page.locator("#jev-config")
    panel.get_by_role("button", name="测试连接", exact=True).click()
    panel.get_by_role("status").filter(has_text="测试成功").wait_for()
    assert (
        len(writes) == 1 and writes[0][0] == "POST" and writes[0][1].endswith("/test")
    )
    assert "api_key" not in writes[0][2]
    panel.get_by_role("button", name="保存配置", exact=True).click()
    page.wait_for_timeout(100)
    assert len(writes) == 2 and writes[1][0] == "PUT"
    assert "api_key" not in writes[1][2]


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (390, 844), (320, 568), (844, 390)]
)
def test_antd_workspace_has_no_errors_or_horizontal_page_overflow(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    settings(page, load)
    for tab in page.get_by_role("tab").all():
        tab.click()
        assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert errors == []


@pytest.mark.parametrize("width", [390, 320])
@pytest.mark.parametrize("admin", [False, True])
def test_antd_mobile_navigation_preserves_role_links_and_focus(ui_page, width, admin):
    page, load = ui_page
    page.set_viewport_size({"width": width, "height": 844})
    settings(page, load, user={"username": "reader", "is_admin": admin})
    trigger = page.get_by_role("button", name="菜单", exact=True)
    trigger.click()
    dialog = page.get_by_role("dialog", name="导航", exact=True)
    dialog.wait_for()
    assert dialog.get_by_role("link", name="管理后台", exact=True).count() == int(admin)
    for link in dialog.get_by_role("link").all():
        box = link.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert box["height"] >= 44
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    assert trigger.evaluate("e => e === document.activeElement")
