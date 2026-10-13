"""Image settings expose active sections without empty cards or a credentials wall."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_ui import settings

SIZES = [(1920, 1080), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]
SERVICES = [
    ("DALL-E", "openai_api_key_image"),
    ("SiliconFlow", "siliconflow_api_key"),
    ("Gemini 图片生成", "gemini_image_api_key"),
    ("OpenAI 图片生成", "openai_image_api_key"),
    ("Pollinations", "pollinations_api_key"),
    ("网络搜索凭据", "unsplash_access_key"),
]


def open_credentials(page, label):
    header = page.locator(".image-credentials-collapse .ant-collapse-header").filter(
        has_text=label
    )
    if header.get_attribute("aria-expanded") != "true":
        header.click()
    return header


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("mode", ["disabled", "ai-only", "all-sources"])
def test_active_image_sections_are_compact_and_never_empty(
    ui_page, width, height, mode
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    settings(
        page,
        load,
        current_config=dict(
            enable_image_service=mode != "disabled",
            enable_ai_generation=mode != "disabled",
            enable_local_images=mode == "all-sources",
            enable_network_search=mode == "all-sources",
        ),
    )
    page.get_by_role("tab", name="图片服务", exact=True).click()
    cards = page.locator("#image-service .config-section-card")
    expect(cards).to_have_count({"disabled": 1, "ai-only": 3, "all-sources": 5}[mode])
    for card in cards.all():
        assert card.locator("input,textarea,button[role=switch]").count()
        box = card.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    expect(
        page.locator(".image-credentials-collapse .ant-collapse-header")
    ).to_have_count(6)
    if width >= 1200:
        assert page.locator("#image-service").bounding_box()["height"] < 1500
        assert page.locator(".image-source-settings").bounding_box()["height"] < 200
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors


@pytest.mark.parametrize("width,height", SIZES)
def test_every_credentials_group_is_accessible_and_keeps_its_draft(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    settings(page, load)
    page.get_by_role("tab", name="图片服务", exact=True).click()
    for label, field in SERVICES:
        header = open_credentials(page, label)
        control = page.locator("#field-" + field)
        expect(control).to_be_visible()
        control.fill("fixture-draft-" + field)
        header.focus()
        header.press("Enter")
        expect(control).not_to_be_visible()
        expect(header).to_be_focused()
        if width <= 600:
            assert header.bounding_box()["height"] >= 44
    page.get_by_role("tab", name="应用配置", exact=True).click()
    page.get_by_role("tab", name="图片服务", exact=True).click()
    for label, field in SERVICES:
        open_credentials(page, label)
        expect(page.locator("#field-" + field)).to_have_value("fixture-draft-" + field)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


@pytest.mark.parametrize("width", [1440, 320])
def test_hidden_sources_and_collapsed_credentials_keep_complete_save_payload(
    ui_page, width
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    writes = []
    page.route(
        "**/api/config/image_service",
        lambda route: (
            writes.append(route.request.post_data_json),
            route.fulfill(json={"success": True}),
        ),
    )
    settings(
        page,
        load,
        current_config=dict(
            enable_image_service=True,
            enable_ai_generation=True,
            enable_local_images=True,
            enable_network_search=True,
            siliconflow_api_key="saved-fixture-key",
            gemini_image_model="saved-fixture-model",
            pixabay_api_key="saved-network-key",
        ),
    )
    page.get_by_role("tab", name="图片服务", exact=True).click()
    expected_names = page.evaluate(
        """() => [...document.querySelector('#settingsBlueprint').content
        .querySelectorAll('#image-service [name]')]
        .filter(field=>field.type==='checkbox'||field.value.trim())
        .map(field=>field.name)"""
    )
    for source, name, value in [
        ("local_images", "max_local_images_per_slide", "4"),
        ("network_search", "max_network_images_per_slide", "3"),
        ("ai_generation", "max_ai_images_per_slide", "2"),
    ]:
        page.locator("#field-" + name).fill(value)
        page.locator("#field-enable_" + source).click()
        expect(page.locator("#field-" + name)).to_have_count(0)
        page.locator("#field-enable_" + source).click()
        expect(page.locator("#field-" + name)).to_have_value(value)
    open_credentials(page, "OpenAI 图片生成")
    page.locator("#field-openai_image_model").fill("custom-image-draft")
    open_credentials(page, "网络搜索凭据")
    page.locator("#field-searxng_host").fill("https://search.example.invalid")
    page.locator("#field-enable_image_service").click()
    expect(page.locator("#image-service .config-section-card")).to_have_count(1)
    page.get_by_role("tab", name="AI 提供者", exact=True).click()
    page.get_by_role("tab", name="图片服务", exact=True).click()
    page.get_by_role("button", name="保存配置", exact=True).click()
    expect(page.get_by_text("配置已保存，已实时生效", exact=True)).to_be_visible()
    assert len(writes) == 1
    config = writes[0]["config"]
    # The original payload omits blank optional credentials; folding must not
    # omit saved credentials or newly edited fields.
    assert set(config) == set(expected_names) | {"openai_image_model", "searxng_host"}
    assert config["siliconflow_api_key"] == "saved-fixture-key"
    assert config["gemini_image_model"] == "saved-fixture-model"
    assert config["pixabay_api_key"] == "saved-network-key"
    assert "unsplash_access_key" not in config
    assert config["enable_image_service"] is False
    for source, name, value in [
        ("local_images", "max_local_images_per_slide", "4"),
        ("network_search", "max_network_images_per_slide", "3"),
        ("ai_generation", "max_ai_images_per_slide", "2"),
    ]:
        assert config["enable_" + source] is True
        assert config[name] == value
    assert config["openai_image_model"] == "custom-image-draft"
    assert config["searxng_host"] == "https://search.example.invalid"
    page.locator("#field-enable_image_service").click()
    expect(page.locator("#field-max_ai_images_per_slide")).to_have_value("2")


def test_changing_default_image_provider_opens_matching_credentials(ui_page):
    page, load = ui_page
    settings(
        page,
        load,
        current_config=dict(
            enable_image_service=True,
            enable_ai_generation=True,
            default_ai_image_provider="openai_image",
        ),
    )
    page.get_by_role("tab", name="图片服务", exact=True).click()
    expect(page.locator("#field-openai_image_model")).to_be_visible()
    page.locator("#field-openai_image_model").fill("unsaved-image-model")
    page.locator("#field-default_ai_image_provider").click()
    page.locator(
        ".ant-select-dropdown:visible .ant-select-item-option-content"
    ).get_by_text("Pollinations (gen.pollinations.ai)", exact=True).click()
    expect(page.locator("#field-pollinations_api_key")).to_be_visible()
    expect(page.locator("#field-pollinations_model")).to_be_visible()
    expect(page.locator("#field-openai_image_model")).not_to_be_visible()
    open_credentials(page, "OpenAI 图片生成")
    expect(page.locator("#field-openai_image_model")).to_have_value(
        "unsaved-image-model"
    )
