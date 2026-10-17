"""Product homepage examples, responsive layout and application entry points."""

import json
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_navigation_ui import navigation_app, open_navigation


SIZES = [(1920, 1080), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


@pytest.mark.parametrize("width,height", SIZES)
def test_design_examples_change_without_layout_jumps_or_generation(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request",
        lambda request: requests.append((request.method, urlsplit(request.url).path)),
    )
    load("pages/home/index.html", path="/home")
    expect(page.get_by_role("heading", level=1)).to_have_text("让想法，成为好演示。")
    group = page.get_by_role("group", name="切换设计示例")
    deck = page.locator(".home-deck")
    original = deck.bounding_box()
    for label, theme, caption in [
        ("数据洞察", "data", "让数据有观点。"),
        ("知识分享", "lesson", "让知识被理解。"),
        ("产品叙事", "story", "把下一步，讲清楚。"),
    ]:
        button = group.get_by_role("button", name=label, exact=True)
        button.click()
        expect(button).to_have_attribute("aria-pressed", "true")
        contrast = button.evaluate(
            r"""element => {
            const luminance = color => {
                const channels = color.match(/[\d.]+/g).slice(0, 3).map(value => {
                    const channel = Number(value) / 255;
                    return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
                });
                return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
            };
            const style = getComputedStyle(element);
            const a = luminance(style.color), b = luminance(style.backgroundColor);
            return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        }"""
        )
        assert contrast >= 4.5
        assert group.locator('[aria-pressed="true"]').count() == 1
        expect(page.locator(f".home-deck-{theme}")).to_be_visible()
        expect(page.locator(".home-example-caption strong")).to_have_text(caption)
        box = deck.bounding_box()
        assert abs(original["height"] - box["height"]) < 1
        assert abs(original["width"] - box["width"]) < 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        for action in group.get_by_role("button").all():
            assert action.bounding_box()["height"] >= (44 if width <= 800 else 40)
    assert not errors
    assert all(method == "GET" for method, _ in requests)
    assert not any(
        path.startswith(("/api/projects", "/api/config")) for _, path in requests
    )
    payload = json.loads(page.locator("#antdData").text_content())
    assert set(payload) == {"page", "user", "creditsEnabled", "sponsors"}
    assert payload["sponsors"] == []
    assert page.locator(".home-sponsors").count() == 0


def test_design_switcher_supports_keyboard_and_reduced_motion(ui_page):
    page, load = ui_page
    page.emulate_media(reduced_motion="reduce")
    load("pages/home/index.html", path="/home")
    buttons = page.get_by_role("group", name="切换设计示例").get_by_role("button")
    buttons.first.focus()
    page.keyboard.press("Tab")
    expect(buttons.nth(1)).to_be_focused()
    page.keyboard.press("Enter")
    expect(buttons.nth(1)).to_have_attribute("aria-pressed", "true")
    expect(buttons.nth(1)).to_be_focused()
    page.keyboard.press("Tab")
    page.keyboard.press("Space")
    expect(buttons.nth(2)).to_have_attribute("aria-pressed", "true")
    assert (
        page.locator(".home-deck-inner").evaluate(
            "e => getComputedStyle(e).animationName"
        )
        == "none"
    )


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844), (320, 568)])
def test_home_workspace_and_creation_are_distinct_pages_with_one_shell(
    ui_page, width, height
):
    page, _ = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = navigation_app(page)
    page.goto("http://ui.test/home", wait_until="networkidle")
    page.evaluate("window.homeHeader=document.querySelector('.app-header')")
    page.get_by_role("link", name="打开工作台", exact=True).click()
    expect(page.get_by_role("heading", name="项目仪表板", exact=True)).to_be_visible()
    assert page.locator(".home-showcase").count() == 0
    assert page.locator(".home-main").count() == 0
    open_navigation(page, "/home")
    expect(page.locator(".home-main")).to_be_visible()
    assert urlsplit(page.url).path == "/home"
    page.get_by_role("link", name="开始创建 PPT", exact=True).click()
    expect(page.get_by_role("heading", name="创建 PPT", exact=True)).to_be_visible()
    assert page.locator(".home-main").count() == 0
    assert page.evaluate("window.homeHeader===document.querySelector('.app-header')")
    assert sum(read["kind"] == "document" for read in state["reads"]) == 1
    assert not state["errors"]


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("count", [1, 6])
def test_home_sponsors_show_profiles_and_keep_actions_reachable(
    ui_page, width, height, count
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors, writes = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request",
        lambda request: writes.append(request.url) if request.method != "GET" else None,
    )
    sponsors = [
        dict(
            nickname=f"支持者 {index}",
            avatar_url=None,
            bio="支持每一个好想法",
            link_url="https://example.invalid",
        )
        for index in range(count)
    ]
    load("pages/home/index.html", path="/home", sponsors=sponsors)
    section = page.get_by_role("region", name="感谢每一份支持", exact=True)
    expect(section).to_be_visible()
    assert section.get_by_role("listitem").count() == count
    expect(
        section.get_by_role("link", name="查看全部赞助", exact=True)
    ).to_have_attribute("href", "/sponsors")
    for index in range(count):
        expect(
            section.get_by_role("heading", name=f"支持者 {index}", exact=True)
        ).to_be_visible()
        link = section.get_by_role(
            "link", name=f"访问 支持者 {index} 的主页", exact=True
        )
        assert link.get_attribute("rel") == "noopener noreferrer"
        if width <= 800:
            assert link.bounding_box()["height"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not writes and not errors


@pytest.mark.parametrize("width", [1440, 320])
def test_home_sponsors_escape_text_reject_unsafe_links_and_bound_cards(ui_page, width):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=900))
    nickname = '<img src=x onerror="window.injected=true">' + "很长的赞助名称" * 15
    sponsor = dict(
        nickname=nickname,
        avatar_url="javascript:alert(1)",
        link_url="javascript:alert(1)",
        bio="long-biography-" * 60,
        private_secret="must-not-be-serialized",
    )
    load("pages/home/index.html", path="/home", sponsors=[sponsor] * 8)
    section = page.get_by_role("region", name="感谢每一份支持", exact=True)
    expect(section).to_be_visible()
    assert section.get_by_role("listitem").count() == 6
    expect(section.get_by_role("heading", level=3).first).to_have_text(nickname)
    assert (
        section.locator('a[href^="javascript:"], img[src^="javascript:"]').count() == 0
    )
    assert "must-not-be-serialized" not in page.content()
    assert not page.evaluate("window.injected || false")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_home_sponsor_link_opens_thanks_page_with_same_shell(ui_page):
    page, _ = ui_page
    state = navigation_app(page)
    sponsors = [
        dict(
            nickname="首页支持者",
            avatar_url=None,
            bio="长期支持",
            link_url=None,
            amount=None,
            note=None,
        )
    ]
    state["overrides"]["/home"] = dict(sponsors=sponsors)
    state["overrides"]["/sponsors"] = dict(sponsors=sponsors)
    page.goto("http://ui.test/home", wait_until="networkidle")
    page.evaluate("window.sponsorHeader = document.querySelector('.app-header')")
    page.get_by_role("link", name="查看全部赞助", exact=True).click()
    expect(page.get_by_role("heading", name="赞助感谢", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="首页支持者", exact=True)).to_be_visible()
    assert page.evaluate(
        "window.sponsorHeader === document.querySelector('.app-header')"
    )
    state["overrides"]["/home"] = dict(sponsors=[])
    open_navigation(page, "/home")
    assert page.locator(".home-sponsors").count() == 0
    assert not state["errors"]
