"""Project search filters before pagination without changing ownership/status."""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from landppt.auth.request_context import current_user_id
from landppt.database.models import Base, Project, User
from landppt.database.repositories import ProjectRepository
from landppt.database.service import DatabaseService


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)


@pytest.fixture
def search_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all(
        [
            User(id=1, username="owner", password_hash="fixture", is_active=True),
            User(id=2, username="other", password_hash="fixture", is_active=True),
        ]
    )
    rows = [
        Project(
            project_id="finance",
            user_id=1,
            title="Finance report",
            topic="预算规划",
            scenario="general",
            updated_at=50,
        ),
        Project(
            project_id="topic-match",
            user_id=1,
            title="产品路线图",
            topic="Research & Strategy",
            scenario="general",
            updated_at=40,
        ),
        Project(
            project_id="literal",
            user_id=1,
            title="50%_growth / budget",
            topic="比例",
            scenario="general",
            updated_at=30,
        ),
        Project(
            project_id="outsider",
            user_id=2,
            title="Finance report",
            topic="Research & Strategy",
            scenario="general",
            updated_at=60,
        ),
    ]
    rows.extend(
        Project(
            project_id=f"owned-{index:02}",
            user_id=1,
            title=f"Research plan {index}",
            topic="测试",
            scenario="general",
            confirmed_requirements={"confirmed": True} if index == 3 else None,
            updated_at=index,
        )
        for index in range(15)
    )
    session.add_all(rows)
    session.commit()
    token = current_user_id.set(1)
    service = DatabaseService(AsyncSessionAdapter(session))
    try:
        yield service
    finally:
        current_user_id.reset(token)
        session.close()
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,expected",
    [
        ("FINANCE", {"finance"}),
        ("预算", {"finance"}),
        ("topic-match", {"topic-match"}),
        ("%", {"literal"}),
        ("_", {"literal"}),
        ("/", {"literal"}),
        ("missing query", set()),
    ],
)
async def test_search_uses_title_topic_id_and_literal_wildcards(
    search_service, query, expected
):
    repo = search_service.project_repo
    rows = await repo.list_projects(search=query, page_size=100)
    assert {row.project_id for row in rows} == expected
    assert await repo.count_projects(search=query) == len(expected)


@pytest.mark.asyncio
async def test_search_total_and_pages_cover_all_owned_matches(search_service):
    first = await search_service.list_projects(
        search="  research  ", page_size=10, user_id=1
    )
    second = await search_service.list_projects(
        search="research", page=2, page_size=10, user_id=1
    )
    assert first.total == second.total == 16
    assert len(first.projects) == 10 and len(second.projects) == 6
    first_ids = {project.project_id for project in first.projects}
    second_ids = {project.project_id for project in second.projects}
    assert not first_ids & second_ids
    assert "topic-match" in first_ids
    assert "outsider" not in first_ids | second_ids
    own_other = await search_service.list_projects(search="finance", user_id=2)
    assert own_other.total == 1
    assert [project.project_id for project in own_other.projects] == ["outsider"]


@pytest.mark.asyncio
async def test_search_keeps_effective_status_and_paginates_after_filter(search_service):
    running = await search_service.list_projects(
        search="research", status="in_progress", user_id=1
    )
    assert running.total == 1
    assert [project.project_id for project in running.projects] == ["owned-03"]
    draft = await search_service.list_projects(
        search="research", status="draft", page=2, page_size=10, user_id=1
    )
    assert draft.total == 15 and len(draft.projects) == 5
    assert "owned-03" not in {project.project_id for project in draft.projects}
    empty = await search_service.list_projects(
        search="missing", status="in_progress", user_id=1
    )
    assert empty.total == 0 and not empty.projects


@pytest.mark.asyncio
async def test_blank_search_preserves_unfiltered_list(search_service):
    response = await search_service.list_projects(
        search="   ", page_size=100, user_id=1
    )
    assert response.total == 18 and len(response.projects) == 18


def test_search_predicate_escapes_postgresql_wildcards():
    clause = ProjectRepository._search_filter("50%_/").compile(
        dialect=postgresql.dialect()
    )
    assert "ESCAPE '/'" in str(clause)
    assert all(value == "50/%/_//" for value in clause.params.values())


@pytest.mark.asyncio
async def test_manager_forwards_search_and_closes_session(monkeypatch):
    from landppt.services.db_project_manager import DatabaseProjectManager
    from unittest.mock import AsyncMock

    service = SimpleNamespace(
        list_projects=AsyncMock(return_value="result"),
        session=SimpleNamespace(close=AsyncMock()),
    )
    manager = DatabaseProjectManager()
    monkeypatch.setattr(manager, "_get_db_service", AsyncMock(return_value=service))
    assert (
        await manager.list_projects(page=2, status="draft", user_id=7, search="query")
        == "result"
    )
    service.list_projects.assert_awaited_once_with(
        2, 10, "draft", user_id=7, search="query"
    )
    service.session.close.assert_awaited_once()


def test_web_query_is_normalized_and_scoped_to_authenticated_user(monkeypatch):
    from landppt.api.models import ProjectListResponse
    from landppt.auth.middleware import get_current_user_required
    from landppt.web.route_modules import project_lifecycle_routes

    calls = []

    class Manager:
        async def list_projects(self, **query):
            calls.append(query)
            return ProjectListResponse(
                projects=[], total=0, page=query["page"], page_size=query["page_size"]
            )

    monkeypatch.setattr(
        project_lifecycle_routes,
        "ppt_service",
        SimpleNamespace(project_manager=Manager()),
    )
    app = FastAPI()
    app.include_router(project_lifecycle_routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        id=17, username="owner", is_admin=False
    )
    with TestClient(app) as client:
        response = client.get(
            "/projects",
            params={"page": 2, "status": "draft", "search": "  Research & 数据  "},
        )
    assert response.status_code == 200
    payload = json.loads(
        response.text.split('<script id="antdData" type="application/json">')[1].split(
            "</script>"
        )[0]
    )
    assert payload["searchQuery"] == "Research & 数据"
    assert calls == [
        dict(page=2, page_size=10, status="draft", user_id=17, search="Research & 数据", sort="pinned")
    ]
