"""The layout contract covers both overflow and undersized content."""

import pytest

from landppt.services.prompts import design_prompts as prompts_module


@pytest.mark.parametrize("entry", ["single", "template"])
@pytest.mark.parametrize("points", [["结论"], ["详细事实" * 25 + str(i) for i in range(8)]])
def test_html_entry_points_preserve_content_and_layout_contract(monkeypatch, entry, points):
    monkeypatch.setattr(prompts_module, "_is_image_service_enabled", lambda: False)
    common = dict(
        slide_data={"title": "分析", "content_points": points},
        page_number=2, total_pages=5, context_info="", style_genes="",
        template_html="<main>REFERENCE</main>",
    )
    if entry == "single":
        prompt = prompts_module.DesignPrompts.get_single_slide_html_prompt(
            **common, confirmed_requirements={})
    else:
        prompt = prompts_module.DesignPrompts.get_creative_template_context_prompt(
            **common, slide_title="分析", slide_type="content")
    assert all(point in prompt for point in points)
    for rule in (
        "1280×720", "无滚动条", "border-box", "min-width:0", "min-height:0",
        "先确定主体的列宽", "文字换行", "纵向堆叠计算高度总和",
        "并列区域取各列高度的最大值", "padding、gap", "为换行误差留余量",
        "放大核心文字或视觉主体", "关键事实、数字及限定条件",
        "不用 ellipsis / line-clamp 截断", "不设统一填充率",
        "禁止为凑满页面编造事实", "<!DOCTYPE html>", "</html>",
    ):
        assert rule in prompt
    assert "75%" not in prompt
    assert "justify-content:space-between" not in prompt
    assert "margin-top:auto" not in prompt
    assert "内容卡片/步骤块/模块默认按内容定高" not in prompt
