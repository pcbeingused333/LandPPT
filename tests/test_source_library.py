"""Source catalogue ownership, JSON projections, literal search and paging."""

import json

import pytest
import pytest_asyncio
from sqlalchemy import event, select

from landppt.database.models import Project
from landppt.web.route_modules import source_library_routes as routes
from test_artifact_library import library  # noqa: F401


@pytest_asyncio.fixture
async def sources(library, monkeypatch):
    monkeypatch.setattr(routes, "AsyncSessionLocal", library.factory)
    library.app.include_router(routes.router)
    async with library.factory() as session:
        mine = await session.scalar(select(Project).where(Project.project_id == "mine"))
        mine.updated_at = 1000
        mine.confirmed_requirements = {
            "content_source": "mixed",
            "uploaded_files": [
                {"filename": "资料%_1.pdf", "file_path": "PRIVATE_STORAGE_A"},
                {
                    "filename": "C:\\PRIVATE_DIR\\original.txt",
                    "file_path": "PRIVATE_STORAGE_B",
                },
            ],
            "source_urls": [
                "https://example.invalid/a?q=1",
                "javascript:alert(1)",
                "https://name:PRIVATE_PASSWORD@example.invalid/",
                "https://example.invalid/b",
                None,
            ],
            "file_generated_outline": {"secret": "PRIVATE_OUTLINE"},
            "merged_file_path": "PRIVATE_MERGED",
            "model": "PRIVATE_MODEL",
        }
        mine.outline, mine.slides_data = {"secret": "PRIVATE_OUTLINE"}, [
            {"html": "PRIVATE_SLIDES"}
        ]
        foreign = await session.scalar(
            select(Project).where(Project.project_id == "foreign")
        )
        foreign.confirmed_requirements = {
            "content_source": "file",
            "uploaded_files": [
                {"filename": "PRIVATE_FOREIGN", "file_path": "PRIVATE_STORAGE"}
            ],
        }
        for index in range(15):
            kind = ["file", "url", "mixed"][index % 3]
            session.add(
                Project(
                    project_id=f"p-{index:02d}",
                    user_id=7,
                    title=(
                        "项目%_"
                        if index == 0
                        else ("project\\name" if index == 1 else f"项目 {index:02d}")
                    ),
                    topic="catalogue",
                    scenario="general",
                    updated_at=index,
                    confirmed_requirements={
                        "content_source": kind,
                        "uploaded_files": [
                            {
                                "filename": "original.txt",
                                "file_path": "PRIVATE_ORIGINAL",
                            }
                        ],
                        "source_urls": (
                            ["https://example.invalid/"]
                            if kind in {"url", "mixed"}
                            else []
                        ),
                    },
                )
            )
        session.add_all(
            [
                Project(
                    project_id="legacy",
                    user_id=7,
                    title="旧附件",
                    topic="legacy",
                    scenario="general",
                    updated_at=30,
                    confirmed_requirements={
                        "content_source": "file",
                        "file_path": "PRIVATE_LEGACY",
                        "filename": "legacy.txt",
                    },
                ),
                Project(
                    project_id="manual",
                    user_id=7,
                    title="无资料",
                    topic="manual",
                    scenario="general",
                    confirmed_requirements={"content_source": "manual"},
                ),
                Project(
                    project_id="malformed",
                    user_id=7,
                    title="旧记录",
                    topic="malformed",
                    scenario="general",
                    updated_at=20,
                    confirmed_requirements={
                        "content_source": "file",
                        "uploaded_files": 123,
                        "source_urls": {"secret": "PRIVATE_MALFORMED"},
                    },
                ),
            ]
        )
        await session.commit()
    return library


async def read(state, **params):
    response = await state.client.get("/api/source-library", params=params)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_owner_filtered_before_pagination_and_only_source_fields_are_public(
    sources, admin
):
    sources.user.is_admin = admin
    first, last = await read(sources), await read(sources, page=100)
    assert first["pagination"] == {"current_page": 1, "per_page": 6, "total_count": 18}
    assert last["pagination"]["current_page"] == 3
    assert first["projects"][0]["id"] == "mine"
    all_projects = (await read(sources, per_page=20))["projects"]
    assert len({item["id"] for item in all_projects}) == 18
    assert not {"foreign", "manual"} & {item["id"] for item in all_projects}
    assert "PRIVATE" not in json.dumps(all_projects)
    assert set(first["projects"][0]) == {
        "id",
        "title",
        "updated_at",
        "source_kind",
        "files",
        "file_count",
        "urls",
        "url_count",
        "invalid_url_count",
    }
    async with sources.factory() as session:
        assert "PRIVATE_SLIDES" in json.dumps(
            (
                await session.scalar(
                    select(Project).where(Project.project_id == "mine")
                )
            ).slides_data
        )


@pytest.mark.asyncio
async def test_sources_keep_original_attachments_hide_derived_url_files_and_unsafe_links(
    sources,
):
    rows = {row["id"]: row for row in (await read(sources, per_page=20))["projects"]}
    assert rows["mine"]["files"] == ["资料%_1.pdf", "original.txt"]
    assert rows["mine"]["file_count"] == 2
    assert rows["mine"]["urls"] == [
        "https://example.invalid/a?q=1",
        "https://example.invalid/b",
    ]
    assert rows["mine"]["url_count"] == 5 and rows["mine"]["invalid_url_count"] == 3
    assert rows["p-01"]["files"] == []  # URL parse cache isn't an attachment.
    assert rows["legacy"]["files"] == ["legacy.txt"]
    assert rows["malformed"]["files"] == rows["malformed"]["urls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,total", [("file", 13), ("url", 11)])
async def test_source_type_and_sort_filter_before_pagination(sources, kind, total):
    result = await read(sources, kind=kind, sort="oldest", per_page=20)
    assert result["pagination"]["total_count"] == total
    assert result["projects"][0]["id"] == ("p-00" if kind == "file" else "p-01")
    assert all(row["source_kind"] in {kind, "mixed"} for row in result["projects"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,ids",
    [
        ("%", ["p-00"]),
        ("_", ["p-00"]),
        ("\\", ["p-01"]),
        ("LEGACY", ["legacy"]),
        ("PRIVATE_FOREIGN", []),
    ],
)
async def test_literal_project_search_is_scoped(sources, query, ids):
    assert [row["id"] for row in (await read(sources, search=query))["projects"]] == ids


@pytest.mark.asyncio
async def test_project_scope_includes_empty_project_and_hides_other_owners_even_for_admin(
    sources,
):
    result = await read(sources, project_id="manual")
    assert result["project"] == {"id": "manual", "title": "无资料"}
    assert (
        result["projects"][0]["files"] == []
        and result["pagination"]["total_count"] == 1
    )
    assert (await read(sources, project_id="manual", kind="file"))["pagination"][
        "total_count"
    ] == 0
    sources.user.is_admin = True
    for identifier in ["foreign", "absent"]:
        response = await sources.client.get(
            "/api/source-library", params={"project_id": identifier}
        )
        assert response.status_code == 404 and "PRIVATE" not in response.text


@pytest.mark.asyncio
async def test_source_arrays_are_bounded_without_misreporting_counts(sources):
    async with sources.factory() as session:
        project = await session.scalar(
            select(Project).where(Project.project_id == "legacy")
        )
        project.confirmed_requirements = {
            "content_source": "mixed",
            "uploaded_files": [
                {"filename": f"{index}.txt", "file_path": f"PRIVATE_{index}"}
                for index in range(60)
            ],
            "source_urls": [f"https://example.invalid/{index}" for index in range(60)],
        }
        await session.commit()
    project = (await read(sources, project_id="legacy"))["projects"][0]
    assert len(project["files"]) == len(project["urls"]) == 50
    assert project["file_count"] == project["url_count"] == 60


@pytest.mark.asyncio
async def test_queries_project_fields_and_sql_json_slices_without_reading_documents(
    sources,
):
    statements = []
    engine = sources.factory.kw["bind"].sync_engine

    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        await read(sources)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) == 2
    assert all(
        "projects.outline" not in query
        and "projects.slides_data" not in query
        and "projects.slides_html" not in query
        for query in statements
    )
    assert "JSON_EXTRACT" in statements[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"per_page": 21},
        {"search": "a" * 201},
        {"kind": "mixed"},
        {"sort": "invalid"},
    ],
)
async def test_invalid_requests_rejected(sources, params):
    assert (
        await sources.client.get("/api/source-library", params=params)
    ).status_code == 422
