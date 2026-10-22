from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _user(user_id: int, *, is_admin: bool = False):
    return SimpleNamespace(id=user_id, is_admin=is_admin)


@pytest.mark.asyncio
async def test_owned_project_helper_scopes_to_authenticated_user(monkeypatch):
    from landppt.services import db_project_manager as db_project_manager_module
    from landppt.web.route_modules import project_workspace_routes

    calls = {}

    class FakeProjectManager:
        async def get_project(self, project_id: str, user_id=None):
            calls["project_id"] = project_id
            calls["user_id"] = user_id
            return SimpleNamespace(project_id=project_id, user_id=user_id)

    monkeypatch.setattr(
        db_project_manager_module, "DatabaseProjectManager", FakeProjectManager
    )

    project = await project_workspace_routes._get_owned_project_or_404(
        "proj-1", _user(42)
    )

    assert project.project_id == "proj-1"
    assert calls == {"project_id": "proj-1", "user_id": 42}


@pytest.mark.asyncio
async def test_owned_project_helper_hides_other_users_projects(monkeypatch):
    from landppt.services import db_project_manager as db_project_manager_module
    from landppt.web.route_modules import project_workspace_routes

    class FakeProjectManager:
        async def get_project(self, project_id: str, user_id=None):
            return None

    monkeypatch.setattr(
        db_project_manager_module, "DatabaseProjectManager", FakeProjectManager
    )

    with pytest.raises(HTTPException) as excinfo:
        await project_workspace_routes._get_owned_project_or_404("proj-2", _user(7))

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Project not found"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("", "todo_board_with_editor.html"),
        ("?view=planning", "todo_board.html"),
        ("?view=planning&auto_start=true", "todo_board.html"),
        ("?view=auto", "todo_board_with_editor.html"),
    ],
)
def test_explicit_planning_view_stays_accessible_after_slides_exist(
    monkeypatch, query, expected
):
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from landppt.auth.middleware import get_current_user_required
    from landppt.web.route_modules import project_workspace_routes as routes

    project = SimpleNamespace(
        project_id="owned",
        topic="Demo",
        confirmed_requirements={"topic": "Demo"},
        outline={"slides": [{"title": "Page"}]},
        slides_data=[{"html_content": "Saved"}],
        project_metadata={},
    )
    manager = SimpleNamespace(get_project=AsyncMock(return_value=project))
    service = SimpleNamespace(
        project_manager=manager,
        get_project_todo_board=AsyncMock(return_value=SimpleNamespace(stages=[])),
    )
    monkeypatch.setattr(routes, "ppt_service", service)
    monkeypatch.setattr(
        routes, "has_active_unattended_run", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        routes,
        "templates",
        SimpleNamespace(
            TemplateResponse=lambda name, context: JSONResponse({"template": name})
        ),
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: _user(7)
    response = TestClient(app).get("/projects/owned/todo" + query)
    assert response.status_code == 200
    assert response.json()["template"] == "pages/project/" + expected
    assert manager.get_project.await_count == 2
    assert all(
        call.kwargs == {"user_id": 7} for call in manager.get_project.await_args_list
    )
