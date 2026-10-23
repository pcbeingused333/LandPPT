"""Project Agent lifecycle. Every operation requires the project owner."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from ...auth.middleware import get_current_user_required
from ...core.config import app_config
from ...database.database import AsyncSessionLocal
from ...database.models import User
from ...services.project_agent_service import MAX_PAGES, ProjectAgentService, TASK_TYPE

router = APIRouter()


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    instruction: str = Field(min_length=1, max_length=8000)
    project_revision: str = Field(min_length=64, max_length=64)
    indices: list[StrictInt] = Field(default_factory=list, max_length=MAX_PAGES)
    previous_task_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def valid_scope(self):
        if any(index < 0 or index > 10000 for index in self.indices) or len(
            set(self.indices)
        ) != len(self.indices):
            raise ValueError("请选择不同的有效页面")
        return self


async def dispatch(task_id):
    from ...services.background_tasks import get_task_manager
    from ...tasks.handlers.project_agent_tasks import run_project_agent
    from ...tasks.queue import enqueue_task

    if str(app_config.task_execution_mode).lower() == "queue":
        await enqueue_task(task_id, TASK_TYPE)
    else:
        manager = get_task_manager()
        task = await manager.get_task_async(task_id)
        manager.running_tasks[task_id] = asyncio.create_task(
            manager.execute_task(task_id, run_project_agent, task)
        )


@router.post("/api/projects/{project_id}/agent")
async def start_agent(
    project_id: str,
    body: AgentRequest,
    response: Response,
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        run = await ProjectAgentService(session).start(
            project_id,
            user.id,
            body.instruction,
            body.indices,
            body.project_revision,
            body.previous_task_id,
        )
        task_id = run.id
    try:
        await dispatch(task_id)
    except Exception:
        # Queue outages leave a retryable terminal record, never a phantom active job.
        from sqlalchemy import update
        from ...database.models import AsyncTask

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(AsyncTask)
                .where(AsyncTask.id == task_id)
                .values(status="failed", error="Task dispatch failed")
            )
            await session.commit()
        raise HTTPException(503, "任务队列暂时不可用，请稍后重试") from None
    return {"success": True, "task_id": task_id}


@router.get("/api/projects/{project_id}/agent")
async def read_agent(
    project_id: str,
    response: Response,
    task_id: str | None = None,
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        service = ProjectAgentService(session)
        return {
            "success": True,
            "task": service.public(await service.task(project_id, user.id, task_id)),
            "context": await service.context(project_id, user.id),
        }


@router.post("/api/projects/{project_id}/agent/{task_id}/cancel")
async def cancel_agent(
    project_id: str,
    task_id: str,
    response: Response,
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        await ProjectAgentService(session).cancel(project_id, user.id, task_id)
    return {"success": True}


@router.post("/api/projects/{project_id}/agent/{task_id}/apply")
async def apply_agent(
    project_id: str,
    task_id: str,
    response: Response,
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        return await ProjectAgentService(session).apply(project_id, user.id, task_id)
