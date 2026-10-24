"""Intent and factual relationships take precedence over decorative quotas."""

from types import SimpleNamespace

import pytest

from landppt.services.prompts import design_prompts as prompts_module
from landppt.services.prompts.design_prompts import DesignPrompts
from landppt.services.slide.creative_design_service import CreativeDesignService


@pytest.mark.parametrize("page,title,expected", [
    (1, "开场", False), (2, "目录", False), (3, "业务分析", True), (5, "结束", False),
])
def test_stable_zones_only_apply_to_regular_template_pages(monkeypatch, page, title, expected):
    monkeypatch.setattr(prompts_module, "_is_image_service_enabled", lambda: False)
    prompt = DesignPrompts.get_single_slide_html_prompt(
        {"title": title}, {}, page, 5, "", "", template_html="<main>REFERENCE</main>")
    assert ("**稳定区域理解方向**" in prompt) == expected
    assert "主体布局由本页内容决定" in prompt


def test_factual_relationships_and_reading_order_precede_dimensions(monkeypatch):
    monkeypatch.setattr(prompts_module, "_is_image_service_enabled", lambda: False)
    prompt = DesignPrompts.get_single_slide_html_prompt({"title": "分析"}, {}, 2, 5, "", "")
    assert prompt.index("**内容与设计质量**") < prompt.index("**固定画布系统**")
    assert "图表、因果和对比关系必须有材料依据" in prompt
    assert "不按要点数量机械套卡片" in prompt
    assert "实际文字/图表/图片" in prompt
    assert "无需输出检查报告或布局注释" in prompt


@pytest.mark.parametrize("page", [1, 2, 5])
def test_fallback_guide_has_no_forced_decoration_or_expansion(page):
    service = CreativeDesignService(SimpleNamespace())
    guide = service._generate_fallback_unified_guide(
        {"title": "数据分析", "content_points": ["结论"]}, page, 5)
    assert "composition_brief" in guide
    assert "以材料为依据" in guide
    assert "至少组合" not in guide
    assert "标题+说明" not in guide
    assert "柱状图" not in guide
    assert "折叠展示" not in guide
    assert len(guide) < 220
