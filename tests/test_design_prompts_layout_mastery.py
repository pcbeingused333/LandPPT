"""Upstream guidance describes a shared system, not another layout manual."""

import pytest

from landppt.services.prompts.design_prompts import DesignPrompts


@pytest.mark.parametrize("entry", ["global", "project", "combined", "genes"])
def test_upstream_prompts_request_compact_visual_tokens(entry):
    template = "<main>UNIQUE_TEMPLATE</main>"
    if entry == "global":
        prompt = DesignPrompts.get_global_visual_constitution_prompt({}, template, 5)
    elif entry == "project":
        prompt = DesignPrompts.get_project_design_guide_prompt({}, "OUTLINE", 5, template_html=template)
        assert "OUTLINE" in prompt
    elif entry == "combined":
        prompt = DesignPrompts.get_combined_style_genes_and_guide_prompt(template, {}, 1, 5)
        for marker in ("STYLE_GENES", "END_STYLE_GENES", "DESIGN_GUIDE", "END_DESIGN_GUIDE"):
            assert prompt.count(f"==={marker}===") == 1
    else:
        prompt = DesignPrompts.get_style_genes_extraction_prompt(template)
    assert prompt.count(template) == 1
    for field in ("palette", "typography", "spacing", "anchors", "components"):
        assert f"- {field}：" in prompt
    assert "500 字" in prompt
    assert "默认值" in prompt
    assert "不指定单页分栏" in prompt
    assert "版式参考工具箱" not in prompt
    assert "**固定画布系统**" not in prompt
    assert len(prompt) < 1400


def test_page_type_guidance_retains_parser_contract_without_visual_rules():
    prompt = DesignPrompts.get_page_creative_briefs_prompt(
        {}, [{"title": "开篇"}, {"title": "比较"}, {"title": "结束"}], 3, "DESIGN_SYSTEM")
    assert "TYPE: cover" in prompt
    assert "TYPE: content" in prompt
    assert "TYPE: ending" in prompt
    assert prompt.count("DESIGN_SYSTEM") == 1
    assert "每种类型最多三行" in prompt
    assert "不重复视觉规范" in prompt
    assert "版式参考工具箱" not in prompt


def test_page_guide_only_requests_page_specific_intent(monkeypatch):
    from landppt.services.prompts import design_prompts
    monkeypatch.setattr(design_prompts, "_is_image_service_enabled", lambda: False)
    prompt = DesignPrompts.get_slide_design_guide_prompt(
        {"title": "分析", "composition_brief": {"focal": "UNIQUE_FOCUS"}}, {},
        "OUTLINE", 2, 5, "<main>STYLE</main>")
    assert prompt.count("UNIQUE_FOCUS") == 1
    assert "任务、关系、焦点、节奏" in prompt
    assert "不重复计划" in prompt
    assert "不规定字号、分栏、模块高度或填充率" in prompt
    assert "版式参考工具箱" not in prompt
    assert "**固定画布系统**" not in prompt
    assert len(prompt) < 900
