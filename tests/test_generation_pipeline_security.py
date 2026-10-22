"""Security regression tests for the outline/PPT generation pipelines."""

import tempfile
from pathlib import Path

import pytest

from landppt.core.file_access import (
    UnsafeFilePathError,
    is_within_allowed_roots,
    sanitize_path_component,
    validate_client_file_path,
)

REPO = Path(__file__).resolve().parents[1]


class TestClientFilePathContainment:
    def test_accepts_file_inside_temp_dir(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
            handle.write(b"hello")
            path = handle.name
        try:
            assert validate_client_file_path(path).exists()
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.parametrize(
        "candidate",
        [
            "",
            "   ",
            None,
        ],
    )
    def test_rejects_empty_paths(self, candidate):
        with pytest.raises(UnsafeFilePathError):
            validate_client_file_path(candidate)

    def test_rejects_project_dotenv(self):
        """The reported arbitrary-read vector: a path outside the upload roots."""
        target = REPO / ".env"
        with pytest.raises(UnsafeFilePathError):
            validate_client_file_path(str(target))

    def test_rejects_traversal_out_of_temp_root(self):
        traversal = Path(tempfile.gettempdir()) / ".." / ".." / "windows" / "win.ini"
        with pytest.raises(UnsafeFilePathError):
            validate_client_file_path(str(traversal))

    def test_rejects_source_tree_paths(self):
        source_file = REPO / "src" / "landppt" / "core" / "config.py"
        assert source_file.exists()
        assert not is_within_allowed_roots(source_file)
        with pytest.raises(UnsafeFilePathError):
            validate_client_file_path(str(source_file))

    def test_rejects_missing_file_inside_root(self):
        missing = Path(tempfile.gettempdir()) / "landppt-does-not-exist-9f3a.txt"
        with pytest.raises(UnsafeFilePathError):
            validate_client_file_path(str(missing))

    def test_null_byte_rejected(self):
        with pytest.raises(UnsafeFilePathError):
            validate_client_file_path("some\x00path.txt")


class TestPathComponentSanitizer:
    @pytest.mark.parametrize(
        "raw,forbidden",
        [
            ("C/C++ 性能优化", "/"),
            ('report: "final"', ':'),
            ("a\\b", "\\"),
            ("what?", "?"),
            ("wild*card", "*"),
            ("pipe|it", "|"),
            ("less<greater>", "<"),
        ],
    )
    def test_strips_reserved_characters(self, raw, forbidden):
        assert forbidden not in sanitize_path_component(raw)

    def test_falls_back_when_everything_stripped(self):
        assert sanitize_path_component("", fallback="topic") == "topic"
        assert sanitize_path_component("...") == "file"

    def test_respects_max_length(self):
        assert len(sanitize_path_component("x" * 200, max_length=30)) == 30


class TestStageStatusValidation:
    """Read the source rather than importing: landppt_api pulls in optional deps."""

    def test_endpoint_validates_status_against_a_whitelist(self):
        source = (REPO / "src" / "landppt" / "api" / "landppt_api.py").read_text(
            encoding="utf-8"
        )
        assert "ALLOWED_STAGE_STATUSES = frozenset(" in source
        assert "if status not in ALLOWED_STAGE_STATUSES" in source

        whitelist = source[source.index("ALLOWED_STAGE_STATUSES = frozenset(") :][:400]
        for expected in ("pending", "running", "completed", "failed", "cancelled"):
            assert f'"{expected}"' in whitelist

    def test_endpoint_validates_progress_range(self):
        source = (REPO / "src" / "landppt" / "api" / "landppt_api.py").read_text(
            encoding="utf-8"
        )
        assert "Progress must be between 0 and 100" in source


class TestCancelEndpointOwnership:
    def test_cancel_routes_load_the_project_first(self):
        source = (
            REPO / "src" / "landppt" / "web" / "route_modules" / "slide_routes.py"
        ).read_text(encoding="utf-8")

        for route in ("/slides/cancel", "/slides/clear-cancel"):
            marker = f'@router.post("/api/projects/{{project_id}}{route}")'
            assert marker in source, f"route {route} not found"
            body = source[source.index(marker) :][:1200]
            assert "get_project(project_id, user_id=user.id)" in body, (
                f"{route} must verify project ownership"
            )
            assert 'status_code=404' in body


class TestOutlineRenderingEscapesModelContent:
    def test_stream_fallback_uses_text_instead_of_model_html(self):
        # React escapes outline fields; stream rendering uses text, never markup.
        view = (REPO / "frontend/src/controllers/outline-stream-view.ts").read_text(encoding="utf-8")
        assert "node.textContent = text" in view
        assert "innerHTML" not in view

    def test_no_unescaped_model_fields_reach_innerhtml(self):
        for name in ["frontend/src/components/todo-outline.tsx", "frontend/src/controllers/outline-controller.ts"]:
            source = (REPO / name).read_text(encoding="utf-8")
            assert "innerHTML" not in source and "dangerouslySetInnerHTML" not in source

    def test_json_editor_keeps_outline_in_a_controlled_value(self):
        source = (REPO / "frontend/src/components/todo-outline.tsx").read_text(encoding="utf-8")
        assert "value={json}" in source
        assert '<Input.TextArea aria-label="页面描述"' in source
        assert "</textarea>" not in source
