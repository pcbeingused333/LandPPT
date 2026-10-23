"""Library persistence, partial writes, ownership and global pagination."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

from landppt.database.models import Base, Project, ProjectLibraryPreference, User
from landppt.database.repositories import ProjectRepository
from landppt.database.service import DatabaseService


class SessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement, params=None):
        return self.session.execute(statement, params or {})

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    def get_bind(self):
        return self.session.get_bind()

    async def connection(self):
        connection = self.session.connection()
        return SimpleNamespace(
            run_sync=AsyncMock(side_effect=lambda fn: fn(connection))
        )


@pytest.fixture
def library_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'library.sqlite3'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id=i, username=f"user-{i}", password_hash="fixture", is_admin=i == 2
                )
                for i in (1, 2)
            ]
        )
        session.flush()
        session.add_all(
            [
                Project(
                    project_id=f"project-{i:02}",
                    user_id=1 if i < 15 else 2,
                    title=f"Research {i}",
                    topic="数据与规划",
                    scenario="general",
                    updated_at=i,
                    created_at=0,
                    version=3,
                    confirmed_requirements={"confirmed": True} if i % 2 else None,
                )
                for i in range(16)
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


@pytest.mark.asyncio
async def test_partial_preferences_persist_without_changing_document(library_db):
    with Session(library_db) as session:
        repo = ProjectRepository(SessionAdapter(session))
        assert await repo.set_library_preferences(
            "project-00", 1, {"is_favorite": True}
        ) == dict(is_favorite=True, is_pinned=False)
        assert await repo.set_library_preferences(
            "project-00", 1, {"is_pinned": True}
        ) == dict(is_favorite=True, is_pinned=True)
        await repo.set_library_preferences("project-00", 1, {"is_pinned": True})
    with Session(library_db) as session:
        service = DatabaseService(SessionAdapter(session))
        project = await service.get_project("project-00", user_id=1)
        assert project.is_favorite and project.is_pinned
        assert (project.updated_at, project.created_at, project.version) == (0, 0, 3)
        assert project.slides_data == [] and project.project_metadata is None
        assert len(session.scalars(select(ProjectLibraryPreference)).all()) == 1
        await service.set_project_library_preferences(
            "project-00", 1, {"is_favorite": False}
        )
    with Session(library_db) as session:
        flags = session.scalar(select(ProjectLibraryPreference))
        assert not flags.is_favorite and flags.is_pinned


@pytest.mark.asyncio
async def test_flags_cannot_be_written_by_another_owner_even_admin(library_db):
    with Session(library_db) as session:
        repo = ProjectRepository(SessionAdapter(session))
        for project_id, user_id in [
            ("missing", 1),
            ("project-00", 2),
            ("project-15", 1),
        ]:
            assert (
                await repo.set_library_preferences(
                    project_id, user_id, {"is_favorite": True}
                )
                is None
            )
        assert not session.scalars(select(ProjectLibraryPreference)).all()


@pytest.mark.asyncio
async def test_another_users_flags_do_not_affect_owner_view(library_db):
    with Session(library_db) as session:
        session.add(
            ProjectLibraryPreference(
                user_id=2, project_id="project-00", is_favorite=True, is_pinned=True
            )
        )
        session.commit()
        service = DatabaseService(SessionAdapter(session))
        assert (await service.list_projects(user_id=1, favorite=True)).total == 0
        project = await service.get_project("project-00", user_id=1)
        assert not project.is_favorite and not project.is_pinned


@pytest.mark.asyncio
async def test_concurrent_sqlite_partial_writes_keep_both_flags(library_db):
    engine = create_async_engine(
        str(library_db.url).replace("sqlite:", "sqlite+aiosqlite:", 1)
    )
    try:

        async def write(changes):
            async with AsyncSession(engine) as session:
                return await ProjectRepository(session).set_library_preferences(
                    "project-00", 1, changes
                )

        await asyncio.gather(write({"is_favorite": True}), write({"is_pinned": True}))
        async with AsyncSession(engine) as session:
            flags = await session.scalar(select(ProjectLibraryPreference))
            assert flags.is_favorite and flags.is_pinned
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_filter_and_pin_order_precede_pagination_and_effective_status(library_db):
    with Session(library_db) as session:
        repo = ProjectRepository(SessionAdapter(session))
        for i in range(16):
            await repo.set_library_preferences(
                f"project-{i:02}",
                1 if i < 15 else 2,
                {"is_favorite": True, "is_pinned": i == 0},
            )
    with Session(library_db) as session:
        service = DatabaseService(SessionAdapter(session))
        first = await service.list_projects(
            user_id=1, search="数据", favorite=True, sort="pinned", page_size=10
        )
        second = await service.list_projects(
            user_id=1, search="数据", favorite=True, sort="pinned", page=2, page_size=10
        )
        assert first.total == second.total == 15 and len(second.projects) == 5
        assert [p.project_id for p in first.projects][:2] == [
            "project-00",
            "project-14",
        ]
        ids = [p.project_id for p in first.projects + second.projects]
        assert len(set(ids)) == 15 and "project-15" not in ids
        recent = await service.list_projects(user_id=1, favorite=True, sort="updated")
        assert recent.projects[0].project_id == "project-14"
        running = await service.list_projects(
            user_id=1,
            favorite=True,
            search="数据",
            sort="pinned",
            status="in_progress",
            page_size=3,
            page=2,
        )
        assert running.total == 7
        assert [p.project_id for p in running.projects] == [
            "project-07",
            "project-05",
            "project-03",
        ]
        other = await service.list_projects(user_id=2, favorite=True)
        assert [p.project_id for p in other.projects] == ["project-15"]


@pytest.mark.asyncio
async def test_failed_upsert_rolls_back_and_can_be_retried(library_db, monkeypatch):
    with Session(library_db) as session:
        adapter = SessionAdapter(session)
        repo = ProjectRepository(adapter)
        commit = adapter.commit
        monkeypatch.setattr(
            adapter, "commit", AsyncMock(side_effect=RuntimeError("write failed"))
        )
        with pytest.raises(RuntimeError, match="write failed"):
            await repo.set_library_preferences("project-00", 1, {"is_favorite": True})
        assert not session.scalars(select(ProjectLibraryPreference)).all()
        monkeypatch.setattr(adapter, "commit", commit)
        assert (
            await repo.set_library_preferences("project-00", 1, {"is_favorite": True})
        )["is_favorite"]


@pytest.mark.asyncio
async def test_deleting_project_removes_library_flags(library_db):
    with Session(library_db) as session:
        repo = ProjectRepository(SessionAdapter(session))
        await repo.set_library_preferences("project-00", 1, {"is_pinned": True})
        assert await repo.delete("project-00", user_id=1)
        assert not session.scalars(select(ProjectLibraryPreference)).all()


@pytest.mark.asyncio
async def test_migration_upgrades_old_sqlite_and_is_idempotent(tmp_path):
    from landppt.database.migrations import DatabaseMigration

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.sqlite3'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c, tables=[User.__table__, Project.__table__]
                )
            )
        async with AsyncSession(engine) as session:
            migration = DatabaseMigration()
            await migration._migration_020_up(session)
            await migration._migration_020_up(session)
            await session.commit()
        async with engine.connect() as conn:
            assert await conn.run_sync(
                lambda c: inspect(c).has_table("project_library_preferences")
            )
        with pytest.raises(RuntimeError, match="automatic rollback is disabled"):
            await migration._migration_020_down(None)
    finally:
        await engine.dispose()


def preference_app(monkeypatch):
    from landppt.api import landppt_api
    from landppt.auth.middleware import get_current_user_required

    manager = SimpleNamespace(
        set_project_library_preferences=AsyncMock(
            return_value=dict(is_favorite=True, is_pinned=False)
        )
    )
    monkeypatch.setattr(
        landppt_api,
        "get_ppt_service_for_user",
        lambda user_id: SimpleNamespace(project_manager=manager),
    )
    app = FastAPI()
    app.include_router(landppt_api.router, prefix="/api")
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        id=17, is_admin=True
    )
    return app, manager


def test_endpoint_requires_auth_and_hides_other_owners(monkeypatch):
    from landppt.auth.middleware import get_current_user_required

    app, manager = preference_app(monkeypatch)
    client = TestClient(app)
    response = client.patch(
        "/api/projects/owned/library-preferences", json={"is_favorite": True}
    )
    assert response.status_code == 200 and response.json()["is_favorite"]
    manager.set_project_library_preferences.assert_awaited_once_with(
        "owned", 17, {"is_favorite": True}
    )
    manager.set_project_library_preferences.return_value = None
    assert (
        client.patch(
            "/api/projects/other/library-preferences", json={"is_pinned": True}
        ).status_code
        == 404
    )
    app.dependency_overrides.pop(get_current_user_required)
    assert (
        client.patch(
            "/api/projects/owned/library-preferences", json={"is_pinned": True}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"is_favorite": None},
        {"is_pinned": "false"},
        {"is_favorite": 1},
        {"is_pinned": True, "user_id": 2},
        {"is_pinned": False, "title": "changed"},
    ],
)
def test_endpoint_rejects_ambiguous_flags_and_unrelated_fields(monkeypatch, body):
    app, manager = preference_app(monkeypatch)
    assert (
        TestClient(app)
        .patch("/api/projects/owned/library-preferences", json=body)
        .status_code
        == 422
    )
    manager.set_project_library_preferences.assert_not_awaited()


def test_api_list_filters_use_authenticated_owner_and_keep_update_default(monkeypatch):
    from landppt.api.models import ProjectListResponse

    app, manager = preference_app(monkeypatch)
    manager.list_projects = AsyncMock(
        return_value=ProjectListResponse(projects=[], total=0, page=1, page_size=10)
    )
    client = TestClient(app)
    response = client.get(
        "/api/projects?favorite=true&sort=pinned&search=%20Research%20&user_id=99"
    )
    assert response.status_code == 200
    manager.list_projects.assert_awaited_once_with(
        page=1,
        page_size=10,
        status=None,
        user_id=17,
        favorite=True,
        sort="pinned",
        search="Research",
    )
    manager.list_projects.reset_mock()
    assert client.get("/api/projects").status_code == 200
    manager.list_projects.assert_awaited_once_with(
        page=1, page_size=10, status=None, user_id=17
    )
    assert client.get("/api/projects?sort=arbitrary").status_code == 422


def test_web_favorite_query_preserves_scope_and_clamps_empty_last_page(monkeypatch):
    from landppt.api.models import ProjectListResponse
    from landppt.auth.middleware import get_current_user_required
    from landppt.web.route_modules import project_lifecycle_routes as routes

    manager = SimpleNamespace(
        list_projects=AsyncMock(
            return_value=ProjectListResponse(
                projects=[], total=10, page=2, page_size=10
            )
        )
    )
    monkeypatch.setattr(routes, "ppt_service", SimpleNamespace(project_manager=manager))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=17)
    response = TestClient(app).get(
        "/projects?favorite=true&search=Research&status=draft&sort=updated&page=2",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith(
        "favorite=true&search=Research&status=draft&sort=updated&page=1"
    )
    manager.list_projects.assert_awaited_once_with(
        page=2,
        page_size=10,
        status="draft",
        search="Research",
        favorite=True,
        user_id=17,
    )
