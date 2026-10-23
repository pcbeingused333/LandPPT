"""Owner-scoped material edits, independent of document and design settings."""

import copy
import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import load_only

from ..database.models import AsyncTask, Project, TodoStage


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def source_files(requirements):
    # URL-only projects also cache downloaded documents here. Those are derived
    # artifacts, not user attachments, and must not be ingested twice.
    if requirements.get("content_source") not in {"file", "mixed"}:
        return []
    files = requirements.get("uploaded_files") or []
    if not files and requirements.get("file_path"):
        files = [
            {
                "file_path": requirements["file_path"],
                "filename": requirements.get("filename", "附件"),
            }
        ]
    return [item for item in files if isinstance(item, dict) and item.get("file_path")]


def _identified_files(requirements):
    return {
        _digest([index, item]): item
        for index, item in enumerate(source_files(requirements))
    }


def _busy_conditions(project_id):
    return (
        select(TodoStage.id)
        .where(TodoStage.project_id == project_id, TodoStage.status == "running")
        .exists(),
        select(AsyncTask.id)
        .where(
            AsyncTask.project_id == project_id,
            AsyncTask.status.in_(["pending", "queued", "running"]),
        )
        .exists(),
    )


class ProjectSourceService:
    def __init__(self, session):
        self.session = session

    async def _project(self, project_id, user_id, *, lock=False):
        statement = (
            select(Project)
            .where(Project.project_id == project_id, Project.user_id == user_id)
            .options(
                load_only(
                    Project.id,
                    Project.project_id,
                    Project.confirmed_requirements,
                    Project.updated_at,
                )
            )
        )
        if lock:
            statement = statement.with_for_update()
        project = await self.session.scalar(statement)
        if project is None:
            raise HTTPException(404, "项目不存在")
        if not project.confirmed_requirements:
            raise HTTPException(409, "请先确认创作需求")
        return project

    @staticmethod
    def _payload(requirements):
        return {
            "revision": _digest(requirements),
            "files": [
                {"id": key, "filename": item.get("filename") or "附件"}
                for key, item in _identified_files(requirements).items()
            ],
            "urls": requirements.get("source_urls") or [],
        }

    async def read(self, project_id, user_id):
        project = await self._project(project_id, user_id)
        busy = any(
            [
                await self.session.scalar(select(condition))
                for condition in _busy_conditions(project_id)
            ]
        )
        return {**self._payload(project.confirmed_requirements), "editable": not busy}

    async def check(self, project_id, user_id, revision, retained, *, lock=False):
        project = await self._project(project_id, user_id, lock=lock)
        if _digest(project.confirmed_requirements) != revision:
            raise HTTPException(
                409,
                "资料或创作设置已在其他窗口更新，请重新打开管理资料；当前草稿已保留",
            )
        if not set(retained).issubset(
            _identified_files(project.confirmed_requirements)
        ):
            raise HTTPException(422, "保留附件无效，请重新打开管理资料")
        if any(
            [
                await self.session.scalar(select(condition))
                for condition in _busy_conditions(project_id)
            ]
        ):
            raise HTTPException(
                409, "项目任务进行中，请完成后再修改资料；当前草稿已保留"
            )
        return project

    async def replace(self, project_id, user_id, revision, retained, uploaded, urls):
        project = await self.check(project_id, user_id, revision, retained, lock=True)
        requirements = copy.deepcopy(project.confirmed_requirements)
        existing = _identified_files(requirements)
        files = [existing[key] for key in retained] + uploaded
        if len(files) > 50:
            raise HTTPException(422, "最多保留 50 个附件")
        for key in (
            "file_path",
            "filename",
            "uploaded_files",
            "merged_file_path",
            "merged_filename",
            "file_generated_outline",
            "file_paths",
        ):
            requirements.pop(key, None)
        requirements.update(
            uploaded_files=files,
            source_urls=urls,
            content_source=(
                "mixed"
                if files and urls
                else "file" if files else "url" if urls else "manual"
            ),
            force_file_outline_regeneration=bool(files or urls),
        )
        if len(files) == 1:
            requirements.update(
                file_path=files[0]["file_path"], filename=files[0]["filename"]
            )
        # Row locks serialize PostgreSQL edits; CAS also protects SQLite and
        # rejects a concurrent project update between the read and this write.
        busy_stage, busy_task = _busy_conditions(project_id)
        result = await self.session.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.user_id == user_id,
                Project.updated_at == project.updated_at,
                ~busy_stage,
                ~busy_task,
            )
            .values(confirmed_requirements=requirements, updated_at=time.time())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(
                409, "项目已更新或任务已开始，请重新打开管理资料；当前草稿已保留"
            )
        await self.session.commit()
        return {**self._payload(requirements), "editable": True}
