"""Templates retain anchors in full context without repeating extracted fragments."""
from landppt.services.prompts.design_prompts import DesignPrompts


# --- Default template HTML with slide-header and slide-footer classes ---
DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<style>
.slide-header { padding: 40px 60px 20px 60px; border-bottom: 2px solid rgba(96,165,250,0.3); }
.slide-title { font-size: 3.5rem; font-weight: bold; color: #60a5fa; }
.slide-footer { position: absolute; bottom: 20px; right: 30px; font-size: 14px; color: #94a3b8; }
</style>
</head>
<body>
<div class="slide-container">
    <div class="slide-header"><h1 class="slide-title">{{ main_heading }}</h1></div>
    <div class="slide-content"><div class="content-main">{{ page_content }}</div></div>
    <div class="slide-footer">{{ current_page_number }} / {{ total_page_count }}</div>
</div>
</body>
</html>"""

# --- Template without semantic class names ---
NO_SEMANTIC_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
.page { width: 1280px; height: 720px; }
</style></head>
<body>
<div class="page">
    <div class="top-bar"><h1>{{ main_heading }}</h1></div>
    <div class="body-area">{{ page_content }}</div>
    <div style="position: absolute; bottom: 10px; right: 20px;">{{ current_page_number }}</div>
</div>
</body>
</html>"""


def test_template_context_retains_header_footer_and_styles():
    context = DesignPrompts._build_template_html_context(DEFAULT_TEMPLATE)
    assert context == DEFAULT_TEMPLATE
    for anchor in ("slide-header", "slide-title", "slide-footer", "current_page_number"):
        assert anchor in context


def test_template_context_retains_anchors_without_semantic_classes():
    context = DesignPrompts._build_template_html_context(NO_SEMANTIC_TEMPLATE)
    assert "current_page_number" in context
    assert "top-bar" in context
    assert "position: absolute" in context


def test_template_context_handles_empty_template():
    assert DesignPrompts._build_template_html_context("") == ""
    assert DesignPrompts._build_template_html_context(None) == ""


def test_locked_zones_context_for_content_page():
    """Content pages receive concise anchor guidance and the original template once."""
    context = DesignPrompts._build_locked_zones_context(
        DEFAULT_TEMPLATE, page_number=3, total_pages=10, slide_type="content")

    assert "稳定区域理解方向" in context
    assert "标题区、页码区" in context
    assert "主内容区重新组织信息" in context
    assert "<style>" not in context and "<div" not in context


def test_locked_zones_context_empty_for_first_page():
    """First page should not get locked zone context."""
    context = DesignPrompts._build_locked_zones_context(
        DEFAULT_TEMPLATE, page_number=1, total_pages=10, slide_type="title")
    assert context == ""


def test_locked_zones_context_empty_for_last_page():
    """Last page should not get locked zone context."""
    context = DesignPrompts._build_locked_zones_context(
        DEFAULT_TEMPLATE, page_number=10, total_pages=10, slide_type="thankyou")
    assert context == ""


def test_locked_zones_context_empty_for_catalog_page():
    """Catalog page should not get locked zone context."""
    context = DesignPrompts._build_locked_zones_context(
        DEFAULT_TEMPLATE, page_number=2, total_pages=10, slide_type="catalog")
    assert context == ""

    # Also test title-based detection
    context2 = DesignPrompts._build_locked_zones_context(
        DEFAULT_TEMPLATE, page_number=2, total_pages=10, slide_type="content",
        slide_title="目录概览")
    assert context2 == ""


def test_locked_zones_fallback_for_unextractable_template():
    """Minimal templates still receive anchor guidance without extraction warnings."""
    minimal_template = "<html><body><div>hello</div></body></html>"
    context = DesignPrompts._build_locked_zones_context(
        minimal_template, page_number=3, total_pages=10, slide_type="content")

    assert "稳定区域理解方向" in context
    assert "模板 HTML 原文" in context
