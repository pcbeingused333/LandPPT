"""Generation routes/bootstrap retain the authenticated identity, never secrets."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from test_app_ui import ROOT, template_environment
from landppt.auth.middleware import get_current_user_required
from landppt.web.route_modules import outline_requirements_routes as routes


def project_fixture(has_outline=True):
    return SimpleNamespace(
        project_id="auth-generator",
        title="页面生成测试",
        topic="认证状态",
        status="completed",
        project_metadata={},
        confirmed_requirements={},
        outline={"slides": [{"title": "测试页"}]} if has_outline else None,
        slides_data=[],
        slides_html=None,
        todo_board=SimpleNamespace(
            task_id="auth-generator", title="页面生成测试", stages=[]
        ),
    )


def bootstrap(html):
    marker = '<script id="antdData" type="application/json">'
    return json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])


@pytest.mark.parametrize("source", ["explicit", "request", "guest"])
@pytest.mark.parametrize("admin", [False, True])
def test_generator_bootstrap_projects_only_public_account_fields(source, admin):
    user = SimpleNamespace(
        username="用户</script><script>alert(1)</script>",
        is_admin=admin,
        password_hash="private-password-hash",
        email="private-email",
        id=7,
    )
    request = SimpleNamespace(
        state=SimpleNamespace(user=user if source == "request" else None)
    )
    values = dict(
        project=project_fixture(),
        request=request,
        credits_enabled=True,
        todo_board=project_fixture().todo_board,
    )
    if source == "explicit":
        values["user"] = user
    html = (
        template_environment(ROOT / "src/landppt/web/templates")
        .get_template("pages/project/todo_board_with_editor.html")
        .render(**values)
    )
    data = bootstrap(html)
    assert data["user"] == (
        None if source == "guest" else {"username": user.username, "is_admin": admin}
    )
    assert data["creditsEnabled"] is True
    assert "private-password-hash" not in html and "private-email" not in html
    assert "<script>alert(1)</script>" not in html


@pytest.mark.asyncio
@pytest.mark.parametrize("has_outline", [False, True])
@pytest.mark.parametrize("admin", [False, True])
async def test_direct_generator_route_carries_dependency_user_without_middleware_state(
    monkeypatch, has_outline, admin
):
    user = SimpleNamespace(id=7, username="authenticated-user", is_admin=admin)
    project = project_fixture(has_outline)

    async def get_project(project_id, user_id):
        assert project_id == project.project_id and user_id == user.id
        return project

    async def active(*args):
        return False

    monkeypatch.setattr(
        routes,
        "ppt_service",
        SimpleNamespace(project_manager=SimpleNamespace(get_project=get_project)),
    )
    monkeypatch.setattr(routes, "has_active_unattended_run", active)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/projects/{project.project_id}/todo-editor")
    assert response.status_code == 200
    data = bootstrap(response.text)
    assert data["page"] == ("generator-workspace" if has_outline else "todo")
    assert data["user"] == {"username": user.username, "is_admin": admin}
