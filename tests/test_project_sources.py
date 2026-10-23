"""Material edits preserve project documents and reject stale/foreign writes."""

import json
import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from test_editor_document_service import documents  # noqa: F401
from test_mixed_source_outline import mixed_flow  # noqa: F401
from test_url_source_research_flow import _project
from landppt.auth.middleware import get_current_user_required
from landppt.database.models import AsyncTask, Project, TodoBoard, TodoStage
from landppt.services.project_source_service import ProjectSourceService
from landppt.web.route_modules import project_source_routes as routes
from landppt.web.route_modules import outline_support


@pytest_asyncio.fixture
async def materials(documents, monkeypatch, tmp_path):
    factory, outline = documents
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(routes, "AsyncSessionLocal", factory)
    original = tmp_path / "existing-project-original.txt"
    original.write_text("ORIGINAL")
    requirements = dict(
        content_source="mixed",
        uploaded_files=[dict(filename="original.txt", file_path=str(original))],
        source_urls=["https://example.invalid/old"],
        audience_type="投资人",
        min_pages=9,
        package_version_id=4,
        file_generated_outline=outline,
        unknown_setting={"keep": True},
    )
    async with factory() as session:
        project = await session.scalar(select(Project))
        project.confirmed_requirements = requirements
        await session.commit()
    app = FastAPI()
    app.include_router(routes.router)
    user = SimpleNamespace(id=7, is_admin=False)
    app.dependency_overrides[get_current_user_required] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield SimpleNamespace(
            factory=factory,
            client=client,
            original=original,
            requirements=requirements,
            user=user,
            tmp_path=tmp_path,
        )


async def read(state):
    result = await state.client.get("/projects/document-test/sources")
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    return result.json()["sources"]


async def save(
    state, snapshot, retained=None, urls="https://example.invalid/new", files=None
):
    return await state.client.post(
        "/projects/document-test/sources",
        data=dict(
            revision=snapshot["revision"],
            retained_files=json.dumps(
                retained
                if retained is not None
                else [item["id"] for item in snapshot["files"]]
            ),
            content_urls=urls,
        ),
        files=files,
    )


@pytest.mark.asyncio
async def test_replace_retains_settings_documents_and_uses_only_owner_file_ids(
    materials,
):
    state = materials
    snapshot = await read(state)
    assert snapshot["editable"] and len(snapshot["files"]) == 1
    assert str(state.original) not in json.dumps(snapshot)
    result = await save(state, snapshot, files=[("file_upload", ("new.txt", b"NEW"))])
    assert result.status_code == 200, result.text
    assert [item["filename"] for item in result.json()["sources"]["files"]] == [
        "original.txt",
        "new.txt",
    ]
    async with state.factory() as session:
        project = await session.scalar(select(Project))
        assert (
            project.outline["title"] == "保留项目标题"
            and project.slides_html == "unchanged combined artwork"
        )
        assert (
            project.slides_data[0]["html_content"] == "unchanged canvas"
            and project.version == 1
        )
        assert project.project_metadata == {"renderer": "svg"}
        requirements = project.confirmed_requirements
        for key in [
            "audience_type",
            "min_pages",
            "package_version_id",
            "unknown_setting",
        ]:
            assert requirements[key] == state.requirements[key]
        assert (
            "file_generated_outline" not in requirements
            and requirements["force_file_outline_regeneration"]
        )
        assert (
            Path(requirements["uploaded_files"][1]["file_path"]).read_bytes() == b"NEW"
        )
    assert state.original.read_text() == "ORIGINAL"


@pytest.mark.asyncio
async def test_clear_all_switches_to_manual_without_deleting_original_or_artwork(
    materials,
):
    result = await save(materials, await read(materials), retained=[], urls="")
    assert result.status_code == 200
    async with materials.factory() as session:
        project = await session.scalar(select(Project))
        req = project.confirmed_requirements
        assert (
            req["content_source"] == "manual"
            and not req["uploaded_files"]
            and not req["source_urls"]
        )
        assert not req["force_file_outline_regeneration"] and "file_path" not in req
        assert project.outline and project.slides_html
    assert materials.original.exists()


@pytest.mark.asyncio
async def test_two_windows_conflict_preserves_confirmed_sources(materials):
    snapshot = await read(materials)
    assert (await save(materials, snapshot)).status_code == 200
    stale = await save(materials, snapshot, urls="https://example.invalid/stale")
    assert stale.status_code == 409
    assert (await read(materials))["urls"] == ["https://example.invalid/new"]


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_foreign_owner_and_missing_project_hidden_before_upload(materials, admin):
    snapshot = await read(materials)
    materials.user.id, materials.user.is_admin = 99, admin
    assert (
        await materials.client.get("/projects/document-test/sources")
    ).status_code == 404
    assert (
        await save(
            materials, snapshot, files=[("file_upload", ("foreign.txt", b"FOREIGN"))]
        )
    ).status_code == 404
    assert not list(materials.tmp_path.glob("temp/project_files/*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retained,urls",
    [
        (["/private/server.txt"], ""),
        (["same", "same"], ""),
        ({"path": "file"}, ""),
        ([], "https://"),
        ([], "ftp://host/file"),
        ([], "https://user:password@host/"),
        ([], "https://host:bad/"),
        ([], "\n".join(f"https://host/{i}" for i in range(51))),
    ],
)
async def test_invalid_selection_rejected_before_bytes_are_saved(
    materials, retained, urls
):
    response = await save(
        materials,
        await read(materials),
        retained=retained,
        urls=urls,
        files=[("file_upload", ("new.txt", b"NEW"))],
    )
    assert response.status_code == 422
    assert not list(materials.tmp_path.glob("temp/project_files/*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["stage", "pending", "queued", "running"])
async def test_active_generation_blocks_source_edits(materials, kind):
    snapshot = await read(materials)
    async with materials.factory() as session:
        if kind == "stage":
            board = TodoBoard(project_id="document-test")
            session.add(board)
            await session.flush()
            session.add(
                TodoStage(
                    project_id="document-test",
                    todo_board_id=board.id,
                    stage_id="outline_generation",
                    stage_index=1,
                    title="outline",
                    description="",
                    status="running",
                )
            )
        else:
            session.add(
                AsyncTask(
                    id="active",
                    task_type="unattended_generation",
                    project_id="document-test",
                    user_id=7,
                    status=kind,
                )
            )
        await session.commit()
    assert not (await read(materials))["editable"]
    assert (await save(materials, snapshot)).status_code == 409


@pytest.mark.asyncio
async def test_conflict_after_upload_cleans_only_new_files(materials, monkeypatch):
    original_save = routes._save_uploaded_files_for_confirmed_requirements

    async def raced(uploads):
        result = await original_save(uploads)
        async with materials.factory() as session:
            project = await session.scalar(select(Project))
            project.confirmed_requirements = {
                **project.confirmed_requirements,
                "min_pages": 12,
            }
            await session.commit()
        return result

    monkeypatch.setattr(
        routes, "_save_uploaded_files_for_confirmed_requirements", raced
    )
    result = await save(
        materials, await read(materials), files=[("file_upload", ("new.txt", b"NEW"))]
    )
    assert result.status_code == 409
    assert (
        not list(materials.tmp_path.glob("temp/project_files/*"))
        and materials.original.exists()
    )


@pytest.mark.asyncio
async def test_partial_upload_failure_cleans_new_files_and_keeps_existing(materials):
    response = await save(
        materials,
        await read(materials),
        files=[
            ("file_upload", ("good.txt", b"GOOD")),
            ("file_upload", ("empty.txt", b"")),
        ],
    )
    assert response.status_code == 422
    assert (
        not list(materials.tmp_path.glob("temp/project_files/*"))
        and materials.original.exists()
    )


@pytest.mark.asyncio
async def test_url_download_cache_is_not_exposed_as_original_upload(materials):
    async with materials.factory() as session:
        project = await session.scalar(select(Project))
        project.confirmed_requirements = {
            **project.confirmed_requirements,
            "content_source": "url",
        }
        await session.commit()
    assert not (await read(materials))["files"]


def test_upload_storage_uses_unique_names_even_for_path_like_client_filenames(
    tmp_path, monkeypatch
):
    from landppt.web.route_modules.outline_support import _save_project_file_sync

    monkeypatch.chdir(tmp_path)
    paths = [
        _save_project_file_sync(value, "../../same.txt") for value in [b"ONE", b"TWO"]
    ]
    assert paths[0] != paths[1]
    assert all(
        Path(path).resolve().parent == (tmp_path / "temp/project_files").resolve()
        for path in paths
    )
    assert [Path(path).read_bytes() for path in paths] == [b"ONE", b"TWO"]


@pytest.mark.asyncio
async def test_cancelled_upload_waits_for_thread_and_removes_only_new_file(
    materials, monkeypatch
):
    from io import BytesIO
    from starlette.datastructures import UploadFile
    from landppt.web.route_modules import outline_support as support

    original_save = support._save_project_file_sync
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), threading.Event()

    def slow_save(*args):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)
        return original_save(*args)

    monkeypatch.setattr(support, "_save_project_file_sync", slow_save)
    task = asyncio.create_task(
        support._save_uploaded_files_for_confirmed_requirements(
            [UploadFile(BytesIO(b"NEW"), filename="new.txt", size=3)]
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not list(materials.tmp_path.glob("temp/project_files/*"))
        and materials.original.exists()
    )


@pytest.mark.asyncio
async def test_disconnect_after_commit_keeps_new_confirmed_file(materials, monkeypatch):
    original_replace = ProjectSourceService.replace

    async def disconnected(self, *args):
        await original_replace(self, *args)
        raise asyncio.CancelledError()

    monkeypatch.setattr(ProjectSourceService, "replace", disconnected)
    with pytest.raises(asyncio.CancelledError):
        await save(
            materials,
            await read(materials),
            files=[("file_upload", ("new.txt", b"NEW"))],
        )
    async with materials.factory() as session:
        project = await session.scalar(select(Project))
        new_file = project.confirmed_requirements["uploaded_files"][-1]
        assert Path(new_file["file_path"]).read_bytes() == b"NEW"
    assert materials.original.exists()


@pytest.mark.asyncio
async def test_task_starting_during_upload_blocks_save_and_cleans_new_files(
    materials, monkeypatch
):
    original_save = routes._save_uploaded_files_for_confirmed_requirements

    async def raced(uploads):
        result = await original_save(uploads)
        async with materials.factory() as session:
            session.add(
                AsyncTask(
                    id="raced",
                    task_type="unattended_generation",
                    project_id="document-test",
                    user_id=7,
                    status="queued",
                )
            )
            await session.commit()
        return result

    monkeypatch.setattr(
        routes, "_save_uploaded_files_for_confirmed_requirements", raced
    )
    result = await save(
        materials, await read(materials), files=[("file_upload", ("new.txt", b"NEW"))]
    )
    assert result.status_code == 409
    assert (
        not list(materials.tmp_path.glob("temp/project_files/*"))
        and materials.original.exists()
    )


@pytest.mark.asyncio
async def test_regeneration_after_replacement_reads_new_sources_without_old_upload(
    materials, mixed_flow
):
    result = await save(
        materials,
        await read(materials),
        retained=[],
        urls="https://example.invalid/replaced",
        files=[("file_upload", ("new.txt", b"NEW_SOURCE_MARKER"))],
    )
    assert result.status_code == 200
    async with materials.factory() as session:
        project = await session.scalar(select(Project))
        requirements = project.confirmed_requirements
    await outline_support._generate_outline_from_confirmed_sources(
        _project(False), requirements, user_id=7
    )
    assert len(mixed_flow.service.generated_requests) == 1
    assert "NEW_SOURCE_MARKER" in mixed_flow.markdowns[0]
    assert "ORIGINAL" not in mixed_flow.markdowns[0]
    assert "This is extracted URL source content" in mixed_flow.markdowns[0]
    assert materials.original.read_text() == "ORIGINAL"
