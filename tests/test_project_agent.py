"""Project tools never cross ownership/scope and artwork batches are atomic."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, select, update

from test_editor_document_service import documents  # noqa: F401
from landppt.ai.base import AIResponse
from landppt.auth.middleware import get_current_user_required
from landppt.database.models import AsyncTask, Project, SlideData, SpeechScript
from landppt.services.project_agent_service import ProjectAgentService
from landppt.services.slide.slide_edit_agent_service import compute_slide_html_hash
from landppt.tasks.handlers import project_agent_tasks as runner
from landppt.web.route_modules import project_agent_routes as routes

URL = "/api/projects/document-test/agent"


@pytest_asyncio.fixture
async def agent(documents, monkeypatch):
    factory, original = documents
    monkeypatch.setattr(routes, "AsyncSessionLocal", factory)
    monkeypatch.setattr(runner, "AsyncSessionLocal", factory)
    dispatches = []

    async def dispatch(task_id):
        dispatches.append(task_id)

    monkeypatch.setattr(routes, "dispatch", dispatch)
    app = FastAPI()
    app.include_router(routes.router)
    user = SimpleNamespace(id=7, is_admin=True)
    app.dependency_overrides[get_current_user_required] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield SimpleNamespace(
            client=client,
            factory=factory,
            user=user,
            dispatches=dispatches,
            original=original,
        )


async def start(agent, **values):
    revision = (await agent.client.get(URL)).json()["context"]["revision"]
    response = await agent.client.post(
        URL,
        json={
            "instruction": "精简所选页内容",
            "indices": [0, 1],
            "project_revision": revision,
            **values,
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["task_id"]


async def proposal(agent, task_id, **values):
    async with agent.factory() as session:
        rows = (
            await session.scalars(select(SlideData).order_by(SlideData.slide_index))
        ).all()
        result = {
            "pages": [
                {
                    "slide_index": row.slide_index,
                    "slide_id": row.slide_id,
                    "title": row.title,
                    "base_hash": compute_slide_html_hash(row.html_content),
                    "html_content": f'<div style="width:1280px;height:720px">修改{row.slide_index}</div>',
                    "diff": "old → new",
                }
                for row in rows
            ],
            **values,
        }
        task = await session.get(AsyncTask, task_id)
        task.status, task.result = "completed", result
        await session.commit()
    return result


@pytest.mark.asyncio
async def test_preview_does_not_save_then_apply_is_atomic_and_idempotent(agent):
    task_id = await start(agent)
    assert agent.dispatches == [task_id]
    draft = await proposal(agent, task_id)
    response = await agent.client.get(URL)
    assert "base_hash" not in str(response.json())
    async with agent.factory() as session:
        assert (
            await session.scalar(select(SlideData).where(SlideData.slide_index == 0))
        ).html_content == "unchanged canvas"
    for _ in range(2):
        result = await agent.client.post(f"{URL}/{task_id}/apply")
        assert result.status_code == 200, result.text
    async with agent.factory() as session:
        rows = (
            await session.scalars(select(SlideData).order_by(SlideData.slide_index))
        ).all()
        assert [row.html_content for row in rows] == [
            item["html_content"] for item in draft["pages"]
        ]
        assert all(row.is_user_edited for row in rows)
        project = await session.scalar(select(Project))
        assert project.slides_data[0]["custom"] == "keep"
        assert project.outline == agent.original
        assert project.slides_html is None and project.project_metadata == {
            "renderer": "svg"
        }
        assert (await session.scalar(select(SpeechScript))).script_content == "原始讲稿"


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["", "/apply", "/cancel"])
async def test_foreign_owner_and_admin_cannot_read_or_operate(agent, endpoint):
    task_id = await start(agent)
    agent.user.id = 99
    if endpoint:
        response = await agent.client.post(f"{URL}/{task_id}{endpoint}")
    else:
        response = await agent.client.get(URL, params={"task_id": task_id})
    assert response.status_code == 404
    assert (
        await agent.client.post(
            URL, json={"instruction": "check", "project_revision": "0" * 64}
        )
    ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["identity", "html", "project", "unsafe", "expired", "cancelled", "busy"]
)
async def test_any_conflict_or_invalid_page_blocks_every_write(agent, kind):
    task_id = await start(agent)
    draft = await proposal(agent, task_id)
    async with agent.factory() as session:
        task = await session.get(AsyncTask, task_id)
        if kind == "identity":
            draft["pages"][1]["slide_id"] = "other"
            task.result = draft
        elif kind == "unsafe":
            draft["pages"][1]["html_content"] = "<div><script>alert(1)</script></div>"
            task.result = draft
        elif kind == "expired":
            task.created_at = 0
        elif kind == "cancelled":
            task.locked_by = "cancel_requested"
        elif kind == "html":
            await session.execute(
                update(SlideData)
                .where(SlideData.slide_index == 1)
                .values(html_content="changed elsewhere")
            )
        elif kind == "project":
            await session.execute(update(Project).values(updated_at=100))
        else:
            session.add(
                AsyncTask(
                    id="busy",
                    project_id="document-test",
                    user_id=7,
                    task_type="export",
                    status="running",
                )
            )
        await session.commit()
    response = await agent.client.post(f"{URL}/{task_id}/apply")
    assert response.status_code in (409, 422), response.text
    async with agent.factory() as session:
        assert (
            await session.scalar(select(SlideData).where(SlideData.slide_index == 0))
        ).html_content == "unchanged canvas"


@pytest.mark.asyncio
async def test_busy_dedup_and_pending_cancel_survive_process_boundary(agent):
    task_id = await start(agent)
    assert (
        await agent.client.post(
            URL,
            json={
                "instruction": "again",
                "project_revision": (await agent.client.get(URL)).json()["context"][
                    "revision"
                ],
            },
        )
    ).status_code == 409
    assert (await agent.client.post(f"{URL}/{task_id}/cancel")).status_code == 200
    async with agent.factory() as session:
        task = await session.get(AsyncTask, task_id)
        assert task.locked_by == "cancel_requested" and task.status == "cancelled"
    assert await runner.cancelled(task_id)
    await start(agent)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"instruction": " "},
        {"instruction": "check", "indices": [0, 0]},
        {"instruction": "check", "indices": [-1]},
        {"instruction": "check", "indices": list(range(11))},
        {"instruction": "check", "indices": [999]},
    ],
)
async def test_invalid_scope_rejected_without_dispatch(agent, body):
    body["project_revision"] = (await agent.client.get(URL)).json()["context"][
        "revision"
    ]
    assert (await agent.client.post(URL, json=body)).status_code == 422
    assert not agent.dispatches


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool",
    [
        "answer",
        "read_pages",
        "edit_pages",
        "open_workspace",
        "invalid",
        "outside",
        "credit",
    ],
)
async def test_real_tool_loop_uses_owned_context_and_never_writes_artwork(
    agent, monkeypatch, tool
):
    task_id = await start(agent)
    charges, calls, progress = [], [], []

    async def check(*args, **kwargs):
        return tool != "credit", 1, 10

    async def charge(*args, **kwargs):
        charges.append(args)
        return True, "ok"

    class Ppt:
        async def get_role_provider_async(self, role):
            return None, {"provider": "test"}

        async def _chat_completion_for_role(self, role, **kwargs):
            calls.append(kwargs)
            action = {
                "tool": tool,
                "summary": "项目检查完成",
                "indices": [0, 1],
                "target": "editor",
            }
            if tool == "read_pages" and len(calls) > 1:
                action["tool"] = "answer"
            if tool == "outside":
                action.update(tool="edit_pages", indices=[2])
            import json

            return AIResponse(content=json.dumps(action), model="test", usage={})

    async def run_slide(self, request, ppt):
        return SimpleNamespace(
            status="completed",
            iterations_used=2,
            proposal=SimpleNamespace(
                changed=True,
                html_content=f"<div>页{request.slideIndex}</div>",
                diff="diff",
                summary="修改完成",
                validation=SimpleNamespace(valid=True),
            ),
        )

    async def update_progress(*args, **kwargs):
        progress.append(kwargs)

    monkeypatch.setattr(runner, "check_credits_for_operation", check)
    monkeypatch.setattr(runner, "consume_credits_for_operation", charge)
    monkeypatch.setattr(runner, "get_ppt_service_for_user", lambda _: Ppt())
    monkeypatch.setattr(
        runner,
        "get_task_manager",
        lambda: SimpleNamespace(update_task_status_async=update_progress),
    )
    monkeypatch.setattr(runner.SlideEditAgentService, "run_agent", run_slide)
    async with agent.factory() as session:
        row = await session.get(AsyncTask, task_id)
        metadata = row.input_data
    result = await runner.run_project_agent(
        SimpleNamespace(task_id=task_id, metadata=metadata)
    )
    if tool in ("invalid", "outside", "credit"):
        assert not result["success"] and not result["pages"]
    else:
        assert result["success"]
        assert len(charges) == (
            3 if tool == "edit_pages" else 2 if tool == "read_pages" else 1
        )
        if tool == "edit_pages":
            assert len(result["pages"]) == 2
        if tool == "open_workspace":
            assert result["link"] == "/projects/document-test/edit"
    async with agent.factory() as session:
        assert (
            await session.scalar(select(SlideData).where(SlideData.slide_index == 0))
        ).html_content == "unchanged canvas"


@pytest.mark.asyncio
async def test_running_provider_is_cancelled_and_cleans_up(agent):
    task_id = await start(agent)
    cleaned = []

    async def work():
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.append(True)

    await agent.client.post(f"{URL}/{task_id}/cancel")
    with pytest.raises(asyncio.CancelledError):
        await runner.interruptible(work(), task_id)
    assert cleaned == [True]


@pytest.mark.asyncio
async def test_legacy_only_artwork_and_apply_receipt_survive_task_cache_refresh(agent):
    async with agent.factory() as session:
        await session.execute(delete(SlideData))
        await session.commit()
    task_id = await start(agent, indices=[0])
    async with agent.factory() as session:
        task = await session.get(AsyncTask, task_id)
        task.status = "completed"
        task.result = {
            "pages": [
                {
                    "slide_index": 0,
                    "slide_id": None,
                    "base_hash": compute_slide_html_hash("unchanged canvas"),
                    "html_content": "<div>legacy modified</div>",
                }
            ]
        }
        await session.commit()
    assert (await agent.client.post(f"{URL}/{task_id}/apply")).status_code == 200
    # Background TaskStore can overwrite its stale result but not the receipt.
    async with agent.factory() as session:
        task = await session.get(AsyncTask, task_id)
        task.result = {"pages": [], "applied": False}
        await session.commit()
    assert (await agent.client.get(URL)).json()["task"]["result"]["applied"]
    assert (await agent.client.post(f"{URL}/{task_id}/apply")).status_code == 200
    async with agent.factory() as session:
        assert (await session.scalar(select(Project))).slides_data[0][
            "html_content"
        ] == "<div>legacy modified</div>"


@pytest.mark.asyncio
async def test_dispatch_failure_releases_busy_gate_and_returns_retryable_error(
    agent, monkeypatch
):
    async def fail(task_id):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(routes, "dispatch", fail)
    response = await agent.client.post(
        URL,
        json={
            "instruction": "check",
            "project_revision": (await agent.client.get(URL)).json()["context"][
                "revision"
            ],
        },
    )
    assert response.status_code == 503
    async with agent.factory() as session:
        assert (await session.scalar(select(AsyncTask))).status == "failed"


@pytest.mark.asyncio
async def test_apply_rechecks_cas_after_page_validation(agent, monkeypatch):
    task_id = await start(agent)
    await proposal(agent, task_id)
    original_pages = ProjectAgentService.pages

    async def race(self, project):
        result = await original_pages(self, project)
        async with agent.factory() as session:
            await session.execute(update(Project).values(updated_at=999))
            await session.commit()
        return result

    monkeypatch.setattr(ProjectAgentService, "pages", race)
    assert (await agent.client.post(f"{URL}/{task_id}/apply")).status_code == 409
    async with agent.factory() as session:
        assert (
            await session.scalar(select(SlideData).where(SlideData.slide_index == 0))
        ).html_content == "unchanged canvas"


@pytest.mark.asyncio
async def test_stale_page_picker_cannot_start_an_edit_on_reordered_pages(agent):
    scope = (await agent.client.get(URL)).json()["context"]
    assert [page["index"] for page in scope["pages"]] == [0, 1]
    assert "html_content" not in str(scope)
    async with agent.factory() as session:
        await session.execute(update(Project).values(updated_at=999))
        await session.commit()
    response = await agent.client.post(
        URL,
        json={
            "instruction": "edit",
            "indices": [0],
            "project_revision": scope["revision"],
        },
    )
    assert response.status_code == 409 and not agent.dispatches


@pytest.mark.asyncio
async def test_page_picker_excludes_empty_normalized_artwork_even_with_old_json(agent):
    async with agent.factory() as session:
        await session.execute(
            update(SlideData).where(SlideData.slide_index == 0).values(html_content="")
        )
        await session.commit()
    scope = (await agent.client.get(URL)).json()["context"]
    assert [page["index"] for page in scope["pages"]] == [1]
