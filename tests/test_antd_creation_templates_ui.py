"""Creation settings and template selection keep the draft until explicit submit."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_creation_research_ui import select
from test_antd_creation_workspace_ui import workspace
from test_antd_templates_ui import selection, template_api


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
def test_settings_drawer_retains_fields_and_returns_keyboard_focus(
    ui_page, width, height
):
    page, _ = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state, calls = workspace(page)
    page.get_by_role("textbox", name="PPT 主题", exact=True).fill("我的演示草稿")
    trigger = page.get_by_role("button", name="高级参数", exact=True)
    trigger.click()
    # The settings tray is inline under the composer, not a dialog.
    drawer = page.locator("#creationAdvanced")
    expect(drawer).to_be_visible()
    expect(page.get_by_role("dialog")).to_have_count(0)
    bounds = drawer.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
    assert bounds["y"] >= 0
    select(page, "目标受众", "自定义")
    drawer.get_by_role("textbox", name="自定义受众描述", exact=True).fill("产品团队")
    if width <= 600:
        assert (
            drawer.get_by_role("textbox", name="自定义受众描述", exact=True).evaluate(
                "node => getComputedStyle(node).fontSize"
            )
            == "16px"
        )
    select(page, "语言", "English")
    collapse = page.locator(".create-advanced-trigger")
    collapse.click()
    expect(drawer).not_to_be_visible()
    expect(collapse).to_be_focused()
    expect(page.locator("#creationAdvancedSummary")).to_contain_text("English")
    trigger.click()
    expect(
        drawer.get_by_role("textbox", name="自定义受众描述", exact=True)
    ).to_have_value("产品团队")
    drawer.get_by_role("textbox", name="自定义受众描述", exact=True).focus()
    page.keyboard.press("Escape")
    expect(drawer).not_to_be_visible()
    expect(collapse).to_be_focused()
    expect(page.get_by_role("textbox", name="PPT 主题", exact=True)).to_have_value(
        "我的演示草稿"
    )
    assert not calls["writes"] and not state["errors"]


@pytest.mark.parametrize(
    "path,width,height",
    [
        ("/dashboard", 1440, 900),
        ("/dashboard", 390, 844),
        ("/dashboard", 320, 568),
        ("/create", 1440, 900),
    ],
)
@pytest.mark.parametrize("choose", [True, False])
def test_package_detail_selection_or_cancel_keeps_draft_and_never_starts_creation(
    ui_page, path, width, height, choose
):
    page, _ = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    navigation, calls = workspace(page, path)
    catalogue = template_api(page)
    page.get_by_role("textbox", name="PPT 主题", exact=True).fill("保留我的主题")
    page.get_by_role("textbox", name="具体需求", exact=True).fill("保留原始需求和附件")
    if path == "/dashboard":
        page.locator(".composer-toolbar .ant-segmented").get_by_text(
            "文件资料", exact=True
        ).click()
    else:
        page.get_by_role("tab", name="文件资料", exact=True).click()
    page.locator("input[type=file]").set_input_files(
        dict(name="source.txt", mimeType="text/plain", buffer=b"keep original file")
    )
    select(page, "生成方式", "快速模式（模板包）")
    browse = page.get_by_role("button", name="浏览模板包", exact=True)
    browse.click()
    picker = page.get_by_role("dialog", name="选择模板包", exact=True)
    expect(picker.locator('[data-package-id="12"]')).to_be_visible()
    expect(picker.locator('[data-package-id="11"]')).to_have_count(0)
    for label in ["编辑草稿", "校验并发布", "AI 创建模板包", "从 PPTX 创建"]:
        expect(picker.get_by_role("button", name=label, exact=True)).to_have_count(0)
    picker.locator('[data-package-id="12"]').get_by_role(
        "button", name="预览", exact=True
    ).click()
    preview = page.get_by_role("dialog", name="公共模板包", exact=True)
    expect(
        preview.get_by_role("button", name="上一个版式", exact=True)
    ).to_be_disabled()
    preview.get_by_role("button", name="下一个版式", exact=True).click()
    expect(
        preview.frame_locator('iframe[title="模板包版式预览"]').get_by_role(
            "heading", name="Original preview", exact=True
        )
    ).to_be_visible()
    expect(preview.get_by_text("版式 2 / 2 · 要点", exact=True)).to_be_visible()
    expect(
        preview.get_by_role("button", name="下一个版式", exact=True)
    ).to_be_disabled()
    preview.get_by_role("button", name="预览版式 1 封面", exact=True).click()
    expect(preview.get_by_text("版式 1 / 2 · 封面", exact=True)).to_be_visible()
    expect(
        preview.get_by_role("button", name="预览版式 1 封面", exact=True)
    ).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    if choose:
        preview.get_by_role("button", name="使用此模板包", exact=True).click()
    else:
        preview.get_by_role("button", name="关闭预览", exact=True).click()
        expect(picker).to_be_visible()
        picker.get_by_role("button", name="返回创建", exact=True).click()
    expect(picker).not_to_be_visible()
    expect(preview).not_to_be_visible()
    expect(browse).to_be_focused()
    expect(page.get_by_role("textbox", name="PPT 主题", exact=True)).to_have_value(
        "保留我的主题"
    )
    expect(page.get_by_role("textbox", name="具体需求", exact=True)).to_have_value(
        "保留原始需求和附件"
    )
    expect(
        page.get_by_role("button", name="移除附件 source.txt", exact=True)
    ).to_be_visible()
    assert not calls["writes"] and not catalogue["writes"]
    page.get_by_role("button", name="开始生成", exact=True).click()
    if choose:
        expect(page.get_by_text("保留草稿供重试", exact=True)).to_be_visible()
        fields, files = calls["writes"][0][3]
        assert fields["package_version_id"] == "12"
        assert fields["render_mode"] == "svg"
        assert fields["topic"] == "保留我的主题"
        assert files == [("file_upload", "source.txt", b"keep original file")]
    else:
        expect(
            page.get_by_text("快速模式需要先选择一个已发布的模板包。", exact=True)
        ).to_be_visible()
        assert not calls["writes"]
    assert not navigation["errors"]


def test_regular_template_can_be_selected_from_preview_without_starting_generation(
    ui_page,
):
    page, load = ui_page
    state = template_api(page)
    selection(page, load)
    card = page.locator('[data-template-id="1"]')
    card.get_by_role("button", name="预览", exact=True).click()
    preview = page.get_by_role("dialog", name="科研汇报母版", exact=True)
    preview.get_by_role("button", name="使用此模板", exact=True).click()
    expect(preview).not_to_be_visible()
    expect(card.get_by_role("button", name="已选择", exact=True)).to_be_visible()
    expect(page.locator(".template-selection-bar")).to_contain_text("科研汇报母版")
    assert not state["writes"]


def test_creation_package_picker_retries_failures_and_explains_no_published_versions(
    ui_page,
):
    page, _ = ui_page
    _, calls = workspace(page)
    catalogue = template_api(page)
    page.get_by_role("textbox", name="PPT 主题", exact=True).fill("网络失败也保留主题")
    select(page, "生成方式", "快速模式（模板包）")
    browse = page.get_by_role("button", name="浏览模板包", exact=True)
    expect(browse).to_be_enabled()

    def unavailable(route):
        route.fulfill(status=503, json={"detail": "模板目录暂不可用"})

    page.route("**/api/global-master-templates/packages", unavailable)
    browse.click()
    picker = page.get_by_role("dialog", name="选择模板包", exact=True)
    expect(picker.get_by_text("模板目录暂不可用", exact=True)).to_be_visible()
    catalogue["packages"] = []
    page.unroute("**/api/global-master-templates/packages", unavailable)
    picker.get_by_role("button", name="重新加载", exact=True).click()
    expect(
        picker.get_by_text(
            "暂无已发布的模板包，可返回创建选择自由设计，或到模板管理发布版本。",
            exact=True,
        )
    ).to_be_visible()
    picker.get_by_role("button", name="返回创建", exact=True).click()
    expect(page.get_by_role("textbox", name="PPT 主题", exact=True)).to_have_value(
        "网络失败也保留主题"
    )
    assert not calls["writes"] and not catalogue["writes"]
