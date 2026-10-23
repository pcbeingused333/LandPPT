"""Owner/expiry filters, literal search and stable server pagination."""

import json
import time
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from landppt.auth.middleware import get_current_user_required
from landppt.database.models import Artifact, Base, Project, User
from landppt.web.route_modules import artifact_library_routes as routes


@pytest_asyncio.fixture
async def library(tmp_path, monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + (tmp_path / "library.db").as_posix()
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = time.time()
    async with factory() as session:
        session.add_all(
            [
                User(id=7, username="owner", password_hash="fixture"),
                User(id=8, username="other", password_hash="fixture"),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Project(
                    project_id="mine",
                    user_id=7,
                    title="研发项目",
                    topic="研发",
                    scenario="general",
                ),
                Project(
                    project_id="foreign",
                    user_id=8,
                    title="不得泄漏的项目",
                    topic="private",
                    scenario="general",
                ),
            ]
        )
        await session.flush()

        def artifact(identifier, **values):
            fields = dict(
                id=identifier,
                user_id=7,
                project_id="mine",
                artifact_type="pdf_export",
                storage_backend="local",
                storage_key="PRIVATE_STORAGE",
                task_id="PRIVATE_TASK",
                filename=identifier + ".pdf",
                content_type="application/pdf",
                size_bytes=100,
                metadata_json={"key": "PRIVATE_METADATA"},
                created_at=10,
                updated_at=10,
            )
            fields.update(values)
            return Artifact(**fields)

        for index in range(25):
            session.add(
                artifact(
                    f"pdf-{index:02d}",
                    filename=(
                        "REPORT%_1.pdf"
                        if index == 1
                        else (
                            "special\\name.pdf"
                            if index == 2
                            else f"deck-{index:02d}.pdf"
                        )
                    ),
                    size_bytes=index * 100,
                    created_at=index,
                )
            )
        session.add_all(
            [
                artifact(
                    "pptx",
                    artifact_type="pptx_export",
                    filename="slides.pptx",
                    created_at=30,
                    size_bytes=5000,
                ),
                artifact(
                    "audio",
                    artifact_type="narration_audio_export",
                    filename="讲解.zip",
                    created_at=30,
                    size_bytes=None,
                ),
                artifact(
                    "video",
                    artifact_type="narration_video_export",
                    filename="讲解.mp4",
                    created_at=30,
                    size_bytes=9000,
                ),
                artifact(
                    "unlinked",
                    artifact_type="narration_video_export",
                    filename="unlinked.mp4",
                    project_id=None,
                    created_at=40,
                    expires_at=now + 3600,
                ),
                artifact("expired", expires_at=now - 1),
                artifact("internal", artifact_type="image_cache"),
                artifact("unsupported", artifact_type="upload"),
                artifact("other-owner", user_id=8, project_id="foreign"),
                artifact("mismatched-project", project_id="foreign"),
                artifact("missing-project", project_id="deleted"),
            ]
        )
        await session.commit()
    monkeypatch.setattr(routes, "AsyncSessionLocal", factory)
    app = FastAPI()
    app.include_router(routes.router)
    user = SimpleNamespace(id=7, is_admin=False)
    app.dependency_overrides[get_current_user_required] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield SimpleNamespace(client=client, factory=factory, user=user, app=app)
    await engine.dispose()


async def read(library, **params):
    response = await library.client.get("/api/artifact-library", params=params)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_filters_owners_expiry_and_internal_types_before_pagination(
    library, admin
):
    library.user.is_admin = admin
    first = await read(library)
    assert first["pagination"] == dict(current_page=1, per_page=20, total_count=29)
    assert len(first["files"]) == 20
    last = await read(library, page=2)
    ids = [row["id"] for row in first["files"] + last["files"]]
    assert len(set(ids)) == 29
    assert not set(ids) & {
        "expired",
        "internal",
        "unsupported",
        "other-owner",
        "mismatched-project",
        "missing-project",
    }
    unlinked = first["files"][0]
    assert unlinked["id"] == "unlinked" and unlinked["project"] is None
    serialized = json.dumps(first, ensure_ascii=False)
    for private in [
        "PRIVATE_STORAGE",
        "PRIVATE_TASK",
        "PRIVATE_METADATA",
        "不得泄漏",
        "storage_backend",
        "storage_key",
        "metadata_json",
        "content_type",
    ]:
        assert private not in serialized
    assert set(unlinked) == {
        "id",
        "filename",
        "category",
        "category_label",
        "file_size",
        "created_at",
        "expires_at",
        "project",
        "download_url",
        "preview_kind",
    }
    assert unlinked["download_url"] == "/api/artifacts/unlinked/download"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category,total", [("pdf", 25), ("pptx", 1), ("audio", 1), ("video", 2)]
)
async def test_category_counts_and_last_page_clamp(library, category, total):
    result = await read(library, category=category, page=100, per_page=10)
    assert result["pagination"]["total_count"] == total
    assert result["pagination"]["current_page"] == (3 if total == 25 else 1)
    assert all(item["category"] == category for item in result["files"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,expected",
    [
        ("report", ["pdf-01"]),
        ("%", ["pdf-01"]),
        ("_", ["pdf-01"]),
        ("\\", ["pdf-02"]),
        ("研发项目", None),
        ("不得泄漏", []),
    ],
)
async def test_literal_filename_and_project_search_are_scoped(library, query, expected):
    result = await read(library, search=query, per_page=100)
    if expected is None:
        assert result["pagination"]["total_count"] == 28
    else:
        assert [item["id"] for item in result["files"]] == expected


@pytest.mark.asyncio
async def test_sort_order_has_stable_ties_and_unknown_sizes_last(library):
    newest = await read(library, per_page=100)
    assert [item["id"] for item in newest["files"][:4]] == [
        "unlinked",
        "video",
        "pptx",
        "audio",
    ]
    oldest = await read(library, per_page=100, sort="oldest")
    assert oldest["files"][0]["id"] == "pdf-00"
    largest = await read(library, per_page=100, sort="largest")
    assert largest["files"][0]["id"] == "video"
    assert largest["files"][-1]["id"] == "audio"


@pytest.mark.asyncio
async def test_project_filter_uses_owner_authority_even_for_admin(library):
    result = await read(library, project_id="mine")
    assert result["project"] == {"id": "mine", "title": "研发项目"}
    assert result["pagination"]["total_count"] == 28
    library.user.is_admin = True
    for identifier in ["foreign", "absent"]:
        response = await library.client.get(
            "/api/artifact-library", params={"project_id": identifier}
        )
        assert response.status_code == 404
    async with library.factory() as session:
        assert len((await session.scalars(select(Artifact))).all()) == 35


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"per_page": 101},
        {"category": "internal"},
        {"sort": "invalid"},
        {"search": "a" * 201},
    ],
)
async def test_invalid_requests_are_rejected(library, params):
    assert (
        await library.client.get("/api/artifact-library", params=params)
    ).status_code == 422
