"""Built Ant preview cards and fullscreen documents, with isolated generation APIs."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_home_generator_ui import ORIGINAL, send, setup_workspace, slide, start


@pytest.mark.parametrize(
    "width,height", [(1440, 900), (390, 844), (320, 568), (844, 390)]
)
def test_native_fullscreen_fits_and_pages_only_through_received_documents(
    ui_page, width, height
):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(3))
    send(page, type="slide", slide_data=slide(1))
    origin = page.get_by_role("button", name="全屏查看第 1 页", exact=True)
    origin.click()
    dialog = page.get_by_role("dialog", name="第 1 页 · 第 1 页", exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("button", name="上一页")).to_be_disabled()
    frame = page.get_by_title("幻灯片全屏预览", exact=True)
    expect(frame).to_have_attribute("srcdoc", ORIGINAL)
    box = frame.bounding_box()
    assert 0 <= box["x"] and box["x"] + box["width"] <= width + 1
    assert 0 <= box["y"] and box["y"] + box["height"] <= height + 1
    assert abs(box["width"] / box["height"] - 16 / 9) < 0.01
    for name in ["上一页", "下一页"]:
        button = dialog.get_by_role("button", name=name)
        assert button.bounding_box()["height"] >= (44 if width <= 600 else 32)
    dialog.get_by_role("button", name="下一页").click()
    dialog = page.get_by_role("dialog", name="第 3 页 · 第 3 页", exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("button", name="下一页")).to_be_disabled()
    expect(dialog.get_by_text("2 / 2", exact=True)).to_be_visible()
    page.keyboard.press("ArrowLeft")
    expect(
        page.get_by_role("dialog", name="第 1 页 · 第 1 页", exact=True)
    ).to_be_visible()
    page.keyboard.press("Escape")
    expect(frame).to_have_count(0)
    expect(origin).to_be_focused()
    assert not errors and not state["writes"]


def test_status_updates_and_adjacent_replacement_do_not_reload_a_saved_document(
    ui_page,
):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    send(page, type="slide", slide_data=slide(1))
    page.wait_for_function(
        "document.querySelector('#slide-1 iframe')?.contentDocument?.body"
    )
    page.evaluate(
        """() => {
        window.originalFrame = document.querySelector('#slide-1 iframe');
        window.originalDocument = originalFrame.contentDocument;
        originalDocument.body.dataset.marker = 'retained';
    }"""
    )
    send(page, type="progress", current=2, total=4, message="正在生成下一页")
    send(page, type="slide", slide_data=slide(2))
    send(
        page,
        type="slide",
        slide_data={**slide(2), "html_content": "<body>Replacement</body>"},
    )
    expect(page.locator("#slide-2 iframe")).to_have_attribute(
        "srcdoc", "<body>Replacement</body>"
    )
    assert page.evaluate(
        """originalFrame === document.querySelector('#slide-1 iframe')
        && originalFrame.contentDocument === originalDocument
        && originalDocument.body.dataset.marker === 'retained'"""
    )
    # Updating metadata alone also preserves the document and displays text safely.
    title = '<img src=x onerror="window.unexpected=true">'
    send(page, type="slide", slide_data={**slide(1), "title": title})
    expect(page.locator("#slide-1 .slide-title")).to_have_text(title)
    assert page.evaluate(
        "originalFrame.contentDocument === originalDocument && !window.unexpected"
    )
    assert page.locator("#slide-1 .slide-header img").count() == 0


def test_keyboard_in_fullscreen_document_respects_inputs_and_releases_old_listeners(
    ui_page,
):
    page, load = ui_page
    setup_workspace(page, load)
    start(page)
    html = '<html><body><input aria-label="页面内输入" value="文字"><button>页面按钮</button></body></html>'
    send(page, type="slide", slide_data={**slide(1), "html_content": html})
    send(page, type="slide", slide_data=slide(2))
    origin = page.get_by_role("button", name="全屏查看第 1 页", exact=True)
    origin.click()
    frame = page.frame_locator('iframe[title="幻灯片全屏预览"]')
    field = frame.get_by_role("textbox", name="页面内输入")
    field.fill("保留的输入")
    field.press("ArrowRight")
    expect(
        page.get_by_role("dialog", name="第 1 页 · 第 1 页", exact=True)
    ).to_be_visible()
    page.evaluate(
        "window.closedDocument = document.querySelector('iframe[title=\"幻灯片全屏预览\"]').contentDocument"
    )
    field.press("Escape")
    expect(page.get_by_title("幻灯片全屏预览", exact=True)).to_have_count(0)
    expect(origin).to_be_focused()
    page.get_by_role("button", name="全屏查看第 2 页", exact=True).click()
    page.evaluate(
        "closedDocument.body.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowLeft', bubbles:true}))"
    )
    expect(
        page.get_by_role("dialog", name="第 2 页 · 第 2 页", exact=True)
    ).to_be_visible()
    # Keyboard events in a noneditable area of the current document navigate.
    current = page.frame_locator('iframe[title="幻灯片全屏预览"]')
    current.locator("body").press("ArrowLeft")
    expect(
        page.get_by_role("dialog", name="第 1 页 · 第 1 页", exact=True)
    ).to_be_visible()
    expect(frame.get_by_role("textbox", name="页面内输入")).to_have_value("文字")
    page.keyboard.press("Escape")


def test_fullscreen_tracks_its_page_during_stream_updates_and_closes_on_pagehide(
    ui_page,
):
    page, load = ui_page
    state = setup_workspace(page, load)
    start(page)
    send(
        page,
        type="slide",
        slide_data={**slide(3), "render_mode": "svg", "generation_failed": True},
    )
    expect(page.locator("#slide-3 .ant-tag[role='status']")).to_have_text("未完成")
    expect(page.locator("#slide-3 .ant-tag[title='SVG 实验页']")).to_have_text("SVG")
    page.get_by_role("button", name="全屏查看第 3 页", exact=True).click()
    send(page, type="slide", slide_data=slide(1))
    expect(
        page.get_by_role("dialog", name="第 3 页 · 第 3 页", exact=True)
    ).to_be_visible()
    replacement = "<html><body><svg><text>Updated SVG</text></svg></body></html>"
    send(
        page,
        type="slide",
        slide_data={**slide(3), "render_mode": "svg", "html_content": replacement},
    )
    expect(page.get_by_title("幻灯片全屏预览", exact=True)).to_have_attribute(
        "srcdoc", replacement
    )
    expect(page.locator("#slide-3 .ant-tag[role='status']")).to_have_count(0)
    page.evaluate(
        "dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}))"
    )
    expect(page.get_by_title("幻灯片全屏预览", exact=True)).to_have_count(0)
    assert not state["writes"]
