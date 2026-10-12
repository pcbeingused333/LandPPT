"""Speech preview visibility and shared task progress, using real editor controllers."""

import pytest
from playwright.sync_api import expect

from test_app_ui import browser, ui_page  # noqa: F401
from test_antd_editor_ui import SCRIPTS, open_scene, setup

SIZES = [(1910, 915), (1440, 900), (1024, 768), (390, 844), (320, 568), (844, 390)]


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("edit", [False, True])
def test_speech_preview_and_editor_never_display_the_same_content_twice(ui_page, width, height, edit):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load)
    dialog = open_scene(page, "speech-preview")
    toggle = dialog.locator("#speechToggleEditModeBtn + [data-native-ant-host] button")
    if edit:
        toggle.click()
    expect(dialog.locator(".speech-script-content")).to_be_hidden() if edit else expect(dialog.locator(".speech-script-content")).to_be_visible()
    expect(dialog.get_by_role("textbox", name="演讲稿内容")).to_have_count(1 if edit else 0)
    if edit:
        expect(dialog.get_by_role("textbox", name="演讲稿内容")).to_have_value(SCRIPTS["scripts"][0]["script_content"])
        expect(dialog.get_by_role("button", name="退出编辑", exact=True)).to_have_count(1)
        assert not dialog.locator("#speechToggleEditModeBtn").is_visible()
    assert not dialog.locator(".speech-script-edit").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert dialog.evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    dialog = open_scene(page, "speech-preview")
    expect(dialog.get_by_role("textbox", name="演讲稿内容")).to_have_count(0)
    assert not state["writes"] and not state["errors"]


def test_individual_edit_and_save_use_one_field_and_the_original_request(ui_page):
    page, load = ui_page
    state = setup(page, load)
    dialog = open_scene(page, "speech-preview")
    item = dialog.locator(".speech-script-item")
    item.get_by_role("button", name="编辑", exact=True).click()
    field = item.get_by_role("textbox", name="演讲稿内容")
    expect(field).to_be_visible()
    expect(item.locator(".speech-script-content")).not_to_be_visible()
    field.fill("保留项目事实，说明接下来的实施步骤。")
    item.get_by_role("button", name="保存", exact=True).click()
    expect(field).not_to_be_visible()
    expect(item.locator(".speech-script-content")).to_have_text("保留项目事实，说明接下来的实施步骤。")
    assert state["writes"] == [("/api/projects/ui-editor/speech-scripts/slide/0", "PUT", {
        "script_content": "保留项目事实，说明接下来的实施步骤。", "slide_title": "封面",
    })]
    assert not state["errors"]


def test_native_control_visibility_survives_class_replacement(ui_page):
    page, load = ui_page
    state = setup(page, load)
    dialog = open_scene(page, "speech-preview")
    button = dialog.locator("#speechToggleEditModeBtn + [data-native-ant-host] button")
    for hide in ["hidden", "d-none"]:
        page.evaluate("name=>{document.getElementById('speechToggleEditModeBtn').className='speech-btn '+name}", hide)
        expect(button).not_to_be_visible()
        page.evaluate("document.getElementById('speechToggleEditModeBtn').className='speech-btn speech-btn-primary'")
        expect(button).to_be_visible()
        assert not dialog.locator("#speechToggleEditModeBtn").is_visible()
    assert not state["errors"]


@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("message,title", [
    ("正在生成全部演讲稿...", "生成演讲稿"),
    ("正在生成中文讲解音频...", "生成讲解音频"),
    ("正在导出中文讲解视频...", "导出讲解视频"),
])
def test_task_progress_moves_into_preview_and_back_without_duplicate_notices(ui_page, width, height, message, title):
    page, load = ui_page
    page.set_viewport_size(dict(width=width, height=height))
    state = setup(page, load, restricted=False)
    page.evaluate("message=>{window.mediaToast=showProgressToast(message)}", message)
    notice = page.locator(".editor-task-notification")
    expect(notice).to_be_visible()
    page.evaluate("updateProgressToast(mediaToast,'正在处理第 2 / 5 页 (37.4%)',37.4)")
    expect(notice.locator(".editor-task-title strong")).to_have_text(title)
    expect(notice.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "37")
    expect(notice.locator(".editor-task-body p")).to_have_text("正在处理第 2 / 5 页")
    assert notice.bounding_box()["x"] >= 0
    assert notice.bounding_box()["x"] + notice.bounding_box()["width"] <= width + 1
    dialog = open_scene(page, "speech-preview")
    expect(notice).not_to_be_visible()
    expect(dialog.locator(".editor-inline-task")).to_have_count(1)
    expect(dialog.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "37")
    page.keyboard.press("Escape")
    expect(notice).to_be_visible()
    expect(page.locator(".editor-inline-task")).to_have_count(0)
    page.evaluate("closeProgressToast(mediaToast)")
    expect(notice).not_to_be_visible()
    assert not state["writes"] and not state["errors"]


def test_unknown_progress_and_reduced_motion_do_not_invent_a_percentage(ui_page):
    page, load = ui_page
    page.emulate_media(reduced_motion="reduce")
    state = setup(page, load)
    page.evaluate("()=>{const node=document.createElement('div');node.id='ai-optimize-loading';node.textContent='正在优化页面内容...';document.body.appendChild(node)}")
    notice = page.locator(".editor-task-notification")
    expect(notice).to_be_visible()
    assert notice.get_by_role("progressbar").count() == 0
    expect(notice.locator(".editor-task-title")).to_contain_text("处理中")
    assert notice.locator(".anticon-spin").evaluate("e=>getComputedStyle(e).animationName") == "none"
    page.evaluate("document.getElementById('ai-optimize-loading').remove()")
    expect(notice).not_to_be_visible()
    assert not state["errors"]


def test_concurrent_jobs_keep_their_own_progress_and_cleanup(ui_page):
    page, load = ui_page
    state = setup(page, load)
    dialog = open_scene(page, "speech-preview")
    page.evaluate("()=>{window.mediaJobs=['正在生成演讲稿','正在生成讲解音频','正在导出讲解视频'].map(message=>showProgressToast(message))}")
    expect(dialog.locator(".editor-inline-task")).to_have_count(3)
    page.evaluate("updateProgressToast(mediaJobs[1],'正在合成第 3 页',66)")
    expect(dialog.get_by_role("progressbar").nth(0)).to_have_attribute("aria-valuenow", "0")
    expect(dialog.get_by_role("progressbar").nth(1)).to_have_attribute("aria-valuenow", "66")
    expect(dialog.get_by_role("progressbar").nth(2)).to_have_attribute("aria-valuenow", "0")
    page.evaluate("closeProgressToast(mediaJobs[1])")
    expect(dialog.locator(".editor-inline-task")).to_have_count(2)
    assert page.locator(".editor-task-notification").count() == 0
    assert not state["errors"]


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_speech_sse_progress_keeps_stream_and_completion_preview_contract(ui_page, terminal):
    page, load = ui_page
    page.add_init_script("""window.mediaStreams=[];window.EventSource=class {
        constructor(url){this.url=url;this.handlers={};this.closed=false;mediaStreams.push(this)}
        addEventListener(name,callback){this.handlers[name]=callback} close(){this.closed=true}
    };window.mediaEvent=(name,progress)=>mediaStreams.at(-1).handlers[name]({data:JSON.stringify({success:true,progress})});""")
    state = setup(page, load)
    requests = []
    page.route("**/speech-script/generate", lambda route: (requests.append(route.request.post_data_json), route.fulfill(json={"success": True, "task_id": "speech-media"})))
    dialog = open_scene(page, "speech")
    dialog.get_by_role("button", name="生成演讲稿", exact=True).click()
    notice = page.locator(".editor-task-notification")
    expect(notice).to_be_visible()
    page.wait_for_function("mediaStreams.length===1")
    page.evaluate("mediaEvent('progress',{status:'running',progress_percentage:46.5,message:'正在编写第 2 页'})")
    expect(notice.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "47")
    page.evaluate("status=>mediaEvent('done',{status,progress_percentage:status==='completed'?100:47,message:status==='completed'?'已保存演讲稿':'写作服务暂时不可用'})", terminal)
    expect(notice).not_to_be_visible()
    assert page.evaluate("mediaStreams[0].closed")
    if terminal == "completed":
        expect(page.locator(".editor-ant-dialog .ant-modal-title")).to_have_text("演讲稿预览")
        expect(page.locator(".editor-inline-task")).to_have_count(0)
        assert page.get_by_role("textbox", name="演讲稿内容").count() == 0
    else:
        expect(page.locator(".ant-message-notice").last).to_contain_text("生成失败")
    assert len(requests) == 1 and requests[0]["generation_type"] == "single"
    assert requests[0]["slide_indices"] == [0] and requests[0]["language"] == "zh"
    assert not state["errors"]


def test_speech_stream_failure_falls_back_to_polling_and_opens_one_preview(ui_page):
    page, load = ui_page
    page.add_init_script("""window.mediaStreams=[];window.EventSource=class {
        constructor(url){this.url=url;this.handlers={};this.closed=false;mediaStreams.push(this)}
        addEventListener(name,callback){this.handlers[name]=callback} close(){this.closed=true}
    };""")
    state = setup(page, load)
    polls, requests = [], []
    page.route("**/speech-script/generate", lambda route: (requests.append(route.request.post_data_json), route.fulfill(json={"success": True, "task_id": "speech-fallback"})))
    page.route("**/speech-scripts/progress/speech-fallback", lambda route: (polls.append(True), route.fulfill(json={"success": True, "progress": {
        "status": "completed", "progress_percentage": 100, "message": "已保存完整演讲稿",
    }})))
    dialog = open_scene(page, "speech")
    dialog.locator('label[for="fullPresentation"]').click()
    expect(dialog.locator('#fullPresentation')).to_be_checked()
    dialog.get_by_role("button", name="生成演讲稿", exact=True).click()
    page.wait_for_function("mediaStreams.length===1")
    page.evaluate("mediaStreams[0].onerror()")
    expect(page.locator(".editor-ant-dialog .ant-modal-title")).to_have_text("演讲稿预览", timeout=8000)
    expect(page.locator(".editor-task-notification")).not_to_be_visible()
    expect(page.locator(".editor-inline-task")).to_have_count(0)
    assert requests[0]["generation_type"] == "full" and requests[0]["slide_indices"] == [0, 1]
    assert len(polls) == 1 and page.evaluate("mediaStreams[0].closed")
    assert page.get_by_role("textbox", name="演讲稿内容").count() == 0
    assert not state["errors"]


def test_failed_speech_save_retains_one_editor_with_the_draft(ui_page):
    page, load = ui_page
    state = setup(page, load)
    page.route("**/speech-scripts/slide/0?language=zh", lambda route: route.fulfill(json={"success": False, "error": "保存服务不可用"}))
    dialog = open_scene(page, "speech-preview")
    dialog.locator(".speech-script-item").get_by_role("button", name="编辑", exact=True).click()
    field = dialog.get_by_role("textbox", name="演讲稿内容")
    field.fill("这是一份需要保留的演讲稿草稿。")
    dialog.get_by_role("button", name="保存", exact=True).click()
    expect(page.locator(".ant-message-notice").last).to_contain_text("保存失败")
    expect(field).to_have_count(1)
    expect(field).to_have_value("这是一份需要保留的演讲稿草稿。")
    expect(dialog.locator(".speech-script-content")).not_to_be_visible()
    expect(dialog.get_by_role("button", name="保存", exact=True)).to_be_enabled()
    assert not state["errors"]


@pytest.mark.parametrize("kind,function,endpoint,label", [
    ("generate", "generateNarrationAudio", "/narration/generate", "生成讲解音频"),
    ("audio", "exportNarrationAudio", "/export/narration-audio", "导出讲解音频"),
    ("video", "exportNarrationVideo", "/export/narration-video", "导出讲解视频"),
])
def test_media_polling_progress_preserves_request_and_downloads(ui_page, kind, function, endpoint, label):
    page, load = ui_page
    state = setup(page, load, restricted=False)
    dialog = open_scene(page, "speech-preview")
    requests, polls = [], []
    progress = {"done": False}
    page.evaluate("()=>{window.mediaDownloads=[];window.triggerFileDownload=url=>mediaDownloads.push(url)}")
    page.route("**" + endpoint, lambda route: (requests.append(route.request.post_data_json), route.fulfill(json={"task_id": "media-task"})))
    def status(route):
        polls.append(True)
        route.fulfill(json={"status": "completed" if progress["done"] else "running", "progress": 100 if progress["done"] else 37,
            "message": "文件已保存" if progress["done"] else "正在处理第 2 页", "download_url": "/downloads/media-fixture"})
    page.route("**/api/landppt/tasks/media-task", status)
    page.evaluate("name=>{window.mediaPromise=window[name]();}", function)
    expect(dialog.locator(".editor-task-title strong")).to_have_text(label)
    expect(dialog.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "37")
    expect(dialog.locator(".editor-task-body p")).to_have_text("正在处理第 2 页")
    assert page.locator(".editor-task-notification").count() == 0
    progress["done"] = True
    expect(dialog.locator(".editor-inline-task")).to_have_count(0, timeout=7000)
    assert page.evaluate("mediaDownloads") == ([] if kind == "generate" else ["/downloads/media-fixture"])
    assert len(requests) == 1 and len(polls) >= 2
    assert requests[0]["language"] == "zh"
    if kind == "video":
        assert requests[0] == {"language": "zh", "fps": 30, "embed_subtitles": True, "subtitle_style": None, "render_mode": "live"}
    else:
        assert requests[0]["provider"] == "edge_tts" and requests[0]["force_regenerate"] is False
    assert not state["errors"]


@pytest.mark.parametrize("failure", ["response", "task", "network"])
def test_video_failure_always_clears_the_progress_card(ui_page, failure):
    page, load = ui_page
    state = setup(page, load, restricted=False)
    dialog = open_scene(page, "speech-preview")
    def begin(route):
        if failure == "network": route.abort()
        elif failure == "response": route.fulfill(status=503, json={"detail": "导出服务不可用"})
        else: route.fulfill(json={"task_id": "failed-media"})
    page.route("**/export/narration-video", begin)
    page.route("**/api/landppt/tasks/failed-media", lambda route: route.fulfill(json={"status": "failed", "progress": 18, "message": "视频渲染失败"}))
    page.evaluate("()=>{exportNarrationVideo()}")
    expect(page.locator(".ant-message-notice").last).to_contain_text("导出失败")
    expect(dialog.locator(".editor-inline-task")).to_have_count(0)
    expect(page.locator(".progress-toast")).to_have_count(0)
    assert page.locator(".editor-task-notification").count() == 0
    assert not state["errors"]
