"""Owner-scoped project tools and atomic application of server-held AI drafts."""

import copy
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select, update

from ..database.models import AsyncTask, Project, SlideData
from .editor_outline_batch_service import _busy, _project_revision
from .slide.slide_edit_agent_service import compute_slide_html_hash, validate_slide_html

TASK_TYPE = "project_agent"
ACTIVE = ("pending", "queued", "running")
MAX_PAGES = 10


class ProjectAgentService:
    def __init__(self, session):
        self.session = session

    async def project(self, project_id, user_id, *, lock=False):
        query = select(Project).where(
            Project.project_id == project_id, Project.user_id == user_id
        )
        project = await self.session.scalar(query.with_for_update() if lock else query)
        if not project:
            raise HTTPException(404, "项目不存在")
        return project

    async def pages(self, project):
        legacy = project.slides_data or []
        rows = (
            await self.session.scalars(
                select(SlideData)
                .where(SlideData.project_id == project.project_id)
                .order_by(SlideData.slide_index)
            )
        ).all()
        result = {
            index: {**item, "slide_index": index}
            for index, item in enumerate(legacy)
            if isinstance(item, dict)
        }
        for row in rows:
            result[row.slide_index] = {
                **result.get(row.slide_index, {}),
                "slide_index": row.slide_index,
                "slide_id": row.slide_id,
                "title": row.title,
                "slide_type": row.content_type,
                "html_content": row.html_content,
            }
        return result, {row.slide_index: row for row in rows}

    async def context(self, project_id, user_id):
        project = await self.project(project_id, user_id)
        choices = {
            index: {"index": index, "title": page.get("title", "")}
            for index, page in enumerate(project.slides_data or [])
            if isinstance(page, dict) and page.get("html_content")
        }
        rows = (
            await self.session.execute(
                select(
                    SlideData.slide_index, SlideData.title, SlideData.html_content != ""
                ).where(SlideData.project_id == project_id)
            )
        ).all()
        for index, title, generated in rows:
            if generated:
                choices[index] = {"index": index, "title": title}
            else:
                choices.pop(index, None)
        return {
            "revision": _project_revision(project),
            "pages": [choices[index] for index in sorted(choices)],
        }

    async def start(
        self,
        project_id,
        user_id,
        instruction,
        indices,
        project_revision,
        previous_task_id=None,
    ):
        project = await self.project(project_id, user_id, lock=True)
        if _project_revision(project) != project_revision:
            raise HTTPException(409, "项目已更新，请刷新任务并重新选择页面后重试")
        pages, _ = await self.pages(project)
        if any(
            index not in pages or not pages[index].get("html_content")
            for index in indices
        ):
            raise HTTPException(422, "所选页面尚未生成，请先完成页面生成")
        previous = ""
        if previous_task_id:
            old = await self.task(project_id, user_id, previous_task_id)
            previous = str((old.result or {}).get("summary", ""))[:4000]
        stage_busy, task_busy = _busy(project_id)
        # Even SQLite serializes this write; two starts cannot both pass the gate.
        gate = await self.session.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.updated_at == project.updated_at,
                ~stage_busy,
                ~task_busy,
            )
            .values(updated_at=project.updated_at)
            .execution_options(synchronize_session=False)
        )
        if gate.rowcount != 1:
            raise HTTPException(409, "项目已有任务运行，请等待完成后重试")
        run = AsyncTask(
            id=str(uuid.uuid4()),
            task_type=TASK_TYPE,
            status="pending",
            user_id=user_id,
            project_id=project_id,
            input_data={
                "project_id": project_id,
                "user_id": user_id,
                "instruction": instruction,
                "indices": indices,
                "previous_summary": previous,
                "project_revision": _project_revision(project),
            },
        )
        self.session.add(run)
        await self.session.commit()
        return run

    async def task(self, project_id, user_id, task_id=None):
        await self.project(project_id, user_id)
        query = select(AsyncTask).where(
            AsyncTask.project_id == project_id,
            AsyncTask.user_id == user_id,
            AsyncTask.task_type == TASK_TYPE,
        )
        query = (
            query.where(AsyncTask.id == task_id)
            if task_id
            else query.order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc()).limit(
                1
            )
        )
        task = await self.session.scalar(query)
        if task_id and not task:
            raise HTTPException(404, "任务不存在")
        return task

    @staticmethod
    def public(task):
        if task is None:
            return None
        result = copy.deepcopy(task.result or {})
        result["applied"] = task.locked_by == "applied"
        # Applying uses the server copy, never a client-supplied HTML replacement.
        for page in result.get("pages", []):
            page.pop("base_hash", None)
            page.pop("html_content", None)
        return {
            "task_id": task.id,
            "status": task.status,
            "progress": task.progress,
            "instruction": task.input_data.get("instruction", ""),
            "indices": task.input_data.get("indices", []),
            "result": result,
            "error": "任务失败，请重试；页面未修改" if task.error else "",
            "cancel_requested": task.locked_by == "cancel_requested",
        }

    async def cancel(self, project_id, user_id, task_id):
        task = await self.task(project_id, user_id, task_id)
        if task.status in ACTIVE:
            values = {"locked_by": "cancel_requested"}
            if task.status in ("pending", "queued"):
                values["status"] = "cancelled"
            await self.session.execute(
                update(AsyncTask)
                .where(AsyncTask.id == task.id, AsyncTask.status.in_(ACTIVE))
                .values(**values)
            )
            await self.session.commit()

    async def apply(self, project_id, user_id, task_id):
        project = await self.project(project_id, user_id, lock=True)
        task = await self.task(project_id, user_id, task_id)
        result = copy.deepcopy(task.result or {})
        if task.locked_by == "applied":
            return {"success": True, "applied": True}
        if (
            task.status != "completed"
            or task.locked_by == "cancel_requested"
            or not result.get("pages")
        ):
            raise HTTPException(409, "任务没有可应用的完整修改")
        if time.time() - task.created_at > 86400:
            raise HTTPException(409, "修改预览已过期，请重新生成")
        if _project_revision(project) != task.input_data.get("project_revision"):
            raise HTTPException(409, "项目已更新，请重新生成预览；本批未保存")
        current, rows = await self.pages(project)
        for page in result["pages"]:
            original = current.get(page["slide_index"], {})
            if (
                original.get("slide_id") != page.get("slide_id")
                or compute_slide_html_hash(original.get("html_content", ""))
                != page["base_hash"]
            ):
                raise HTTPException(409, "页面已更新或顺序已改变；本批未保存")
            validation = validate_slide_html(
                page["html_content"], baseline_html=original.get("html_content", "")
            )
            if not validation.valid:
                raise HTTPException(422, "修改预览未通过安全校验；本批未保存")
        stage_busy, task_busy = _busy(project_id)
        stamp = time.time()
        gate = await self.session.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.updated_at == project.updated_at,
                ~stage_busy,
                ~task_busy,
            )
            .values(updated_at=stamp)
            .execution_options(synchronize_session=False)
        )
        if gate.rowcount != 1:
            raise HTTPException(409, "项目已更新或任务运行中；本批未保存")
        legacy = copy.deepcopy(project.slides_data or [])
        for page in result["pages"]:
            index = page["slide_index"]
            patch = {"html_content": page["html_content"], "is_user_edited": True}
            if index in rows:
                rows[index].html_content = patch["html_content"]
                rows[index].is_user_edited = True
            if index < len(legacy):
                legacy[index] = {**legacy[index], **patch}
        project.slides_data, project.updated_at = legacy, stamp
        # A combined HTML cache must not expose the artwork from before this edit.
        project.slides_html = None
        result["applied"] = True
        task.result = result
        # TaskStore owns result/status and can refresh them from another worker's
        # cache. It never writes locked_by, so this receipt cannot be reverted.
        task.locked_by = "applied"
        await self.session.commit()
        return {"success": True, "applied": True}
