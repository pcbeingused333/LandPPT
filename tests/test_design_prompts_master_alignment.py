"""Both HTML entry points share one design system without dropping user inputs."""

import copy

import pytest

from landppt.services.prompts import design_prompts as prompts_module


@pytest.fixture(params=["single", "template"])
def build_prompt(request, monkeypatch):
    monkeypatch.setattr(prompts_module, "_is_image_service_enabled", lambda: False)

    def build(**overrides):
        common = dict(
            slide_data={"title": "报告", "content_points": ["收入 42 万元（未审计）"]},
            template_html="<main>REFERENCE</main>", page_number=2, total_pages=5,
            context_info="PAGE_ROLE", style_genes="LEGACY_GENES",
            global_constitution="DESIGN_SYSTEM", current_page_brief="PAGE_INTENT",
        )
        include_page_numbers = overrides.pop("include_page_numbers", True)
        common.update(overrides)
        if request.param == "single":
            return prompts_module.DesignPrompts.get_single_slide_html_prompt(
                **common, confirmed_requirements={
                    "topic": "PROJECT_TOPIC", "target_audience": "AUDIENCE",
                    "include_page_numbers": include_page_numbers,
                })
        return prompts_module.DesignPrompts.get_creative_template_context_prompt(
            **common, slide_title=common["slide_data"]["title"], slide_type="content",
            project_topic="PROJECT_TOPIC", project_audience="AUDIENCE",
            include_page_numbers=include_page_numbers)
    return build


def test_one_authoritative_design_system_and_intact_inputs(build_prompt):
    slide = {
        "title": "报告", "content_points": ["收入 42 万元（未审计）"],
        "composition_brief": {"focal": "UNIQUE_FOCUS", "relation": "UNIQUE_RELATION"},
        "images_summary": "https://example.test/image.png",
    }
    original = copy.deepcopy(slide)
    prompt = build_prompt(slide_data=slide)
    for value in (
        "DESIGN_SYSTEM", "PAGE_INTENT", "PAGE_ROLE", "REFERENCE", "PROJECT_TOPIC",
        "AUDIENCE", "收入 42 万元（未审计）", "UNIQUE_FOCUS", "UNIQUE_RELATION",
        "https://example.test/image.png",
    ):
        assert prompt.count(value) == 1
    assert "LEGACY_GENES" not in prompt
    assert slide == original
    assert prompt.count("**整套设计系统**") == 1
    assert prompt.count("**固定画布系统**") == 1
    assert "用户明确要求优先" in prompt
    assert len(prompt) < 2200


@pytest.mark.parametrize("system", ["", "   "])
def test_legacy_genes_are_used_when_design_system_missing(build_prompt, system):
    prompt = build_prompt(global_constitution=system)
    assert prompt.count("LEGACY_GENES") == 1


def test_no_guidance_or_template_still_produces_complete_prompt(build_prompt):
    prompt = build_prompt(global_constitution="", style_genes="", template_html="", current_page_brief="")
    assert "无模板时建立简洁一致的视觉规范" in prompt
    assert "1280×720" in prompt
    assert "<!DOCTYPE html>" in prompt
    assert "收入 42 万元（未审计）" in prompt


def test_page_number_opt_out_keeps_layout_and_content_constraints(build_prompt):
    prompt = build_prompt(
        include_page_numbers=False,
        context_info="页码沿用模板位置。",
        global_constitution="DESIGN_SYSTEM\n页码放在右下角。",
        template_html="<main>REFERENCE</main>\n<footer>{{ current_page_number }}</footer>",
    )
    for token in ("页码", "Footer", "footer", "current_page_number"):
        assert token not in prompt
    assert "DESIGN_SYSTEM" in prompt
    assert "收入 42 万元（未审计）" in prompt
    assert "1280×720" in prompt
    assert "先确定主体的列宽" in prompt
    assert "<!DOCTYPE html>" in prompt


def test_single_entry_preserves_custom_requirements(monkeypatch):
    monkeypatch.setattr(prompts_module, "_is_image_service_enabled", lambda: False)
    prompt = prompts_module.DesignPrompts.get_single_slide_html_prompt(
        {"title": "报告"}, {"custom_style_prompt": "CUSTOM_STYLE", "description": "REQUIREMENT"},
        2, 5, "", "")
    assert "CUSTOM_STYLE" in prompt
    assert "REQUIREMENT" in prompt
