"""Mixed materials must reach one outline request without losing source identity."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from test_create_render_mode import creation  # noqa: F401
from test_url_source_research_flow import (
    FakePPTService,
    _confirmed_requirements,
    _patch_url_flow,
    _project,
)
from landppt.services.file_processor import FileProcessor
from landppt.web.route_modules import outline_support as support


@pytest.fixture
def mixed_flow(monkeypatch, tmp_path):
    class Service(FakePPTService):
        async def generate_outline_from_file(self, request):
            markdowns.append(Path(request.file_path).read_text(encoding="utf-8"))
            return await super().generate_outline_from_file(request)

    markdowns, parsed = [], []
    service = Service(tmp_path)
    _patch_url_flow(monkeypatch, tmp_path, service)
    original = tmp_path / "original.txt"
    original.write_text("LOCAL_MARKER", encoding="utf-8")
    requirements = {
        **_confirmed_requirements(),
        "content_source": "mixed",
        "uploaded_files": [{"filename": "original.txt", "file_path": str(original)}],
    }

    async def process(self, path, filename, file_processing_mode="markitdown"):
        parsed.append((filename, file_processing_mode))
        return SimpleNamespace(processed_content=Path(path).read_text(encoding="utf-8"))

    monkeypatch.setattr(FileProcessor, "process_file", process)
    return SimpleNamespace(
        service=service,
        requirements=requirements,
        original=original,
        markdowns=markdowns,
        parsed=parsed,
        tmp_path=tmp_path,
    )


@pytest.mark.asyncio
async def test_mixed_sources_merge_before_one_outline_and_keep_originals(mixed_flow):
    state = mixed_flow
    result = await support._generate_outline_from_confirmed_sources(
        _project(False), state.requirements, user_id=7
    )
    assert len(state.service.generated_requests) == 1
    assert state.markdowns[0].count("LOCAL_MARKER") == 1
    assert "This is extracted URL source content" in state.markdowns[0]
    assert "Use recent market facts." in state.markdowns[0]
    assert result["file_info"]["source_type"] == "mixed"
    assert result["file_info"]["sources_count"] == 2
    assert result["file_info"]["uploaded_files"] == state.requirements["uploaded_files"]
    assert result["metadata"]["llm_call_count"] == 2
    assert state.original.read_text() == "LOCAL_MARKER"


@pytest.mark.asyncio
async def test_regeneration_does_not_reingest_the_previous_merged_document(
    monkeypatch, mixed_flow
):
    state = mixed_flow
    first = await support._generate_outline_from_confirmed_sources(
        _project(False), state.requirements, user_id=7
    )
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "landppt.services.db_project_manager.DatabaseProjectManager",
        lambda: SimpleNamespace(save_confirmed_requirements=save),
    )
    updated = await support._persist_generated_source_outline(
        "project-1", state.requirements, first, user_id=7
    )
    save.assert_awaited_once()
    assert updated["uploaded_files"] == state.requirements["uploaded_files"]
    assert updated["source_urls"] == state.requirements["source_urls"]
    await support._generate_outline_from_confirmed_sources(
        _project(False), updated, user_id=7
    )
    assert len(state.service.generated_requests) == 2
    assert state.markdowns[-1].count("LOCAL_MARKER") == 1
    assert state.markdowns[-1].count("This is extracted URL source content") == 1


@pytest.mark.asyncio
async def test_mixed_sources_research_receives_the_combined_document(mixed_flow):
    state = mixed_flow
    await support._generate_outline_from_confirmed_sources(
        _project(True), state.requirements, user_id=7
    )
    research = state.service.research_calls[0]
    merged = Path(research["file_paths"][0]).read_text(encoding="utf-8")
    assert "LOCAL_MARKER" in merged and "This is extracted URL source content" in merged
    assert (
        len(state.service.research_calls) == len(state.service.generated_requests) == 1
    )


@pytest.mark.asyncio
async def test_uploads_downloaded_files_and_web_pages_all_reach_the_outline(
    monkeypatch, mixed_flow
):
    state = mixed_flow
    remote = "https://example.com/download.txt"
    state.requirements["source_urls"].append(remote)
    state.requirements["file_processing_mode"] = "magic_pdf"
    monkeypatch.setattr(
        support,
        "_url_likely_points_to_file",
        AsyncMock(side_effect=lambda session, url: url == remote),
    )

    async def download(**kwargs):
        path = state.tmp_path / "downloaded.txt"
        path.write_text("REMOTE_FILE_MARKER")
        return dict(
            source_url=remote,
            resolved_url=remote,
            filename="downloaded.txt",
            file_path=str(path),
            size=18,
            content_type="text/plain",
        )

    monkeypatch.setattr(support, "_download_supported_file_from_url", download)
    result = await support._generate_outline_from_confirmed_sources(
        _project(False), state.requirements, user_id=7
    )
    assert all(
        marker in state.markdowns[0]
        for marker in [
            "LOCAL_MARKER",
            "REMOTE_FILE_MARKER",
            "This is extracted URL source content",
        ]
    )
    assert result["url_info"]["downloaded_files_count"] == 1
    assert result["file_info"]["uploaded_files"] == state.requirements["uploaded_files"]
    assert state.parsed == [
        ("original.txt", "magic_pdf"),
        ("downloaded.txt", "magic_pdf"),
    ]


@pytest.mark.asyncio
async def test_unreadable_upload_does_not_fall_back_to_url_only(
    monkeypatch, mixed_flow
):
    state = mixed_flow
    monkeypatch.setattr(
        FileProcessor,
        "process_file",
        AsyncMock(side_effect=ValueError("parser failed")),
    )
    with pytest.raises(ValueError, match="original.txt"):
        await support._generate_outline_from_confirmed_sources(
            _project(False), state.requirements, user_id=7
        )
    assert not state.service.generated_requests and state.original.exists()


@pytest.mark.asyncio
async def test_failed_url_does_not_fall_back_to_upload_only(monkeypatch, mixed_flow):
    state = mixed_flow
    monkeypatch.setattr(
        "landppt.services.research.content_extractor.WebContentExtractor.extract_multiple",
        AsyncMock(return_value=[]),
    )
    with pytest.raises(ValueError, match="未生成不完整的大纲"):
        await support._generate_outline_from_confirmed_sources(
            _project(False), state.requirements, user_id=7
        )
    assert not state.service.generated_requests and state.original.exists()


@pytest.mark.asyncio
async def test_cancel_cleans_generated_material_but_keeps_original_upload(
    monkeypatch, mixed_flow
):
    state = mixed_flow
    entered = asyncio.Event()

    async def wait_for_cancel(request):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(state.service, "generate_outline_from_file", wait_for_cancel)
    task = asyncio.create_task(
        support._generate_outline_from_confirmed_sources(
            _project(False), state.requirements, user_id=7
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(state.tmp_path.iterdir()) == [state.original]


@pytest.mark.asyncio
async def test_mixed_stream_preserves_done_counts_and_source_metadata(
    monkeypatch, mixed_flow
):
    state = mixed_flow
    persist = AsyncMock(return_value=state.requirements)
    monkeypatch.setattr(support, "_persist_generated_source_outline", persist)
    chunks = [
        chunk
        async for chunk in support._stream_outline_from_confirmed_sources_v2(
            "project-1", _project(False), state.requirements, user_id=7
        )
    ]
    events = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in chunks]
    assert any(
        "合并文件与网页" in event.get("status", {}).get("message", "")
        for event in events
    )
    assert events[-1] == {"done": True, "llm_call_count": 2}
    assert persist.call_args.args[2]["file_info"]["source_type"] == "mixed"


def test_creation_persists_both_inputs_without_extraction(
    creation, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        support,
        "_save_project_file_sync",
        lambda content, name: _save(tmp_path / name, content),
    )
    generate = AsyncMock()
    monkeypatch.setattr(support, "_process_url_sources_for_outline", generate)
    with TestClient(creation.app) as client:
        response = client.post(
            "/projects/create-and-confirm",
            data={
                "topic": "mixed",
                "audience_type": "普通大众",
                "content_source": "mixed",
                "content_urls": "https://example.com/article\nhttps://example.com/article",
            },
            files=[("file_upload", ("notes.txt", b"LOCAL", "text/plain"))],
        )
    assert response.status_code == 200, response.text
    confirmed = (
        creation.service.confirm_requirements_and_update_workflow.call_args.args[1]
    )
    assert confirmed["source_urls"] == ["https://example.com/article"]
    assert Path(confirmed["uploaded_files"][0]["file_path"]).read_bytes() == b"LOCAL"
    assert confirmed["force_file_outline_regeneration"]
    assert creation.manager.create_project.call_args.args[0].use_file_content
    generate.assert_not_awaited()


def _save(path, content):
    path.write_bytes(content)
    return str(path)


@pytest.mark.asyncio
async def test_unattended_mixed_stage_uses_source_stream_and_actual_call_count(
    monkeypatch,
):
    from test_unattended_mode import _FakeProject, _FakeService, _runner, _wire

    project = _FakeProject(
        confirmed_requirements={
            "content_source": "mixed",
            "force_file_outline_regeneration": True,
        }
    )
    service = _FakeService(project)
    runner = _runner("outline")
    _wire(runner, service, project)
    runner._resolve_provider = AsyncMock(return_value="custom")
    runner._require_credits = AsyncMock()
    runner._charge_credits = AsyncMock()
    calls = []

    async def stream(project_id, current_project, confirmed, *, user_id):
        calls.append((project_id, user_id, confirmed["content_source"]))
        project.outline = {"slides": [{"title": "Mixed"}]}
        yield 'data: {"done": true, "llm_call_count": 2}\n\n'

    monkeypatch.setattr(support, "_stream_outline_from_confirmed_sources_v2", stream)
    await runner._run_outline()
    assert calls == [("project-1", 7, "mixed")]
    assert not any(call[0] == "generate_outline_streaming" for call in service.calls)
    assert runner.stages["outline"].status == "completed"
    assert runner._charge_credits.call_args.args[:3] == (
        "outline_generation",
        2,
        "custom",
    )


@pytest.mark.parametrize(
    "source,urls,attach",
    [
        ("mixed", "", True),
        ("mixed", "https://example.com/a", False),
        ("unknown", "", True),
    ],
)
def test_invalid_mixed_inputs_fail_before_project_or_files_are_created(
    creation, monkeypatch, source, urls, attach
):
    save = AsyncMock()
    monkeypatch.setattr(
        support, "_save_uploaded_files_for_confirmed_requirements", save
    )
    with TestClient(creation.app) as client:
        response = client.post(
            "/projects/create-and-confirm",
            data={"topic": "mixed", "content_source": source, "content_urls": urls},
            files=(
                [("file_upload", ("notes.txt", b"LOCAL", "text/plain"))]
                if attach
                else None
            ),
        )
    assert response.status_code == 422
    creation.manager.create_project.assert_not_awaited()
    save.assert_not_awaited()


def test_confirmation_preserves_mixed_inputs_and_checks_owner_first(
    creation, monkeypatch, tmp_path
):
    from landppt.web.route_modules import outline_requirements_routes as routes

    creation.app.include_router(routes.router)
    creation.manager.get_project = AsyncMock(return_value=_project(False))
    monkeypatch.setattr(
        routes, "get_ppt_service_for_user", lambda uid: creation.service
    )
    monkeypatch.setattr(
        routes, "maybe_start_unattended_run", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        support,
        "_save_project_file_sync",
        lambda content, name: _save(tmp_path / name, content),
    )
    with TestClient(creation.app) as client:
        response = client.post(
            "/projects/project-1/confirm-requirements",
            data={
                "topic": "mixed",
                "content_source": "mixed",
                "content_urls": "https://example.com/a",
                "audience_type": "普通大众",
            },
            files=[("file_upload", ("notes.txt", b"LOCAL", "text/plain"))],
        )
        assert response.status_code == 200, response.text
        confirmed = (
            creation.service.confirm_requirements_and_update_workflow.call_args.args[1]
        )
        assert (
            confirmed["content_source"] == "mixed"
            and len(confirmed["uploaded_files"]) == len(confirmed["source_urls"]) == 1
        )
        creation.manager.get_project.assert_awaited_once_with("project-1", user_id=7)
        creation.manager.get_project.return_value = None
        assert (
            client.post(
                "/projects/other/confirm-requirements",
                data={
                    "topic": "mixed",
                    "audience_type": "普通大众",
                    "content_source": "mixed",
                },
            ).status_code
            == 404
        )
