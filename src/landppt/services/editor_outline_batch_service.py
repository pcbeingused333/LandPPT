"""Atomic, revision-checked title/type edits without rewriting page artwork."""

import copy
import json
import time

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import load_only

from ..database.models import AsyncTask, Project, SlideData, TodoStage
from .editor_document_service import _document_revision, _outline_block, _revision


def _busy(project_id):
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


def _project_revision(project):
    return _revision([project.project_id, project.updated_at])


class EditorOutlineBatchService:
    def __init__(self, session):
        self.session = session

    async def _load(self, project_id, user_id, indices, *, lock=False):
        if (
            not indices
            or len(indices) > 50
            or len(set(indices)) != len(indices)
            or any(index < 0 for index in indices)
        ):
            raise HTTPException(422, "请选择 1 至 50 个不同的页面")
        query = (
            select(Project)
            .where(Project.project_id == project_id, Project.user_id == user_id)
            .options(
                load_only(
                    Project.id, Project.project_id, Project.outline, Project.updated_at
                )
            )
        )
        project = await self.session.scalar(query.with_for_update() if lock else query)
        if project is None:
            raise HTTPException(404, "项目不存在")
        rows = (
            await self.session.scalars(
                select(SlideData)
                .where(
                    SlideData.project_id == project_id,
                    SlideData.slide_index.in_(indices),
                )
                .options(
                    load_only(
                        SlideData.id,
                        SlideData.slide_index,
                        SlideData.slide_id,
                        SlideData.title,
                        SlideData.content_type,
                        SlideData.slide_metadata,
                    )
                )
            )
        ).all()
        by_index = {row.slide_index: row for row in rows}
        outline = copy.deepcopy(project.outline or {})
        blocks, legacy = outline.get("slides") or [], []
        if len(by_index) != len(indices):
            await self.session.refresh(project, ["slides_data"])
            legacy = project.slides_data or []
        documents = []
        for index in indices:
            slide = by_index.get(index)
            if slide is None and index >= max(len(blocks), len(legacy)):
                raise HTTPException(
                    409, "页面已删除或顺序已改变，请重新读取；草稿已保留"
                )
            identity = (
                slide.slide_id
                if slide
                else legacy[index].get("slide_id") if index < len(legacy) else None
            )
            block = _outline_block(blocks, legacy, slide, index)
            documents.append(
                dict(
                    slide_index=index,
                    slide_id=identity,
                    outline=block,
                    outline_revision=_document_revision("outline", block),
                )
            )
        busy = any(
            [await self.session.scalar(select(clause)) for clause in _busy(project_id)]
        )
        return project, outline, by_index, documents, busy

    async def read(self, project_id, user_id, indices):
        project, _, _, pages, busy = await self._load(project_id, user_id, indices)
        return dict(
            project_revision=_project_revision(project), pages=pages, editable=not busy
        )

    async def save(self, project_id, user_id, body):
        indices = [item.slide_index for item in body.pages]
        project, outline, slides, documents, busy = await self._load(
            project_id, user_id, indices, lock=True
        )
        if body.project_revision != _project_revision(project):
            raise HTTPException(
                409, "项目已在其他窗口更新，请重新读取后核对；本批未保存，草稿已保留"
            )
        if busy:
            raise HTTPException(
                409, "项目任务进行中，完成后再保存；本批未保存，草稿已保留"
            )
        # Validate every selected page before changing any ORM object.
        for item, document in zip(body.pages, documents):
            if (
                item.slide_id != document["slide_id"]
                or item.revision != document["outline_revision"]
            ):
                raise HTTPException(
                    409,
                    f"第 {item.slide_index + 1} 页已更新，请重新读取；本批未保存，草稿已保留",
                )
        stamp = time.time()
        stage_busy, task_busy = _busy(project_id)
        result = await self.session.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.user_id == user_id,
                Project.updated_at == project.updated_at,
                ~stage_busy,
                ~task_busy,
            )
            .values(updated_at=stamp)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "项目已更新或任务已开始；本批未保存，草稿已保留")
        await self.session.refresh(project, ["slides_data"])
        legacy = copy.deepcopy(project.slides_data or [])
        blocks = outline.setdefault("slides", [])
        for item, document in zip(body.pages, documents):
            patch = item.changes.model_dump(exclude_unset=True)
            merged = {**document["outline"], **patch}
            if "slide_type" in patch:
                merged["type"] = patch["slide_type"]
            while len(blocks) <= item.slide_index:
                blocks.append({})
            blocks[item.slide_index] = merged
            slide = slides.get(item.slide_index)
            if slide:
                if "title" in patch:
                    slide.title = patch["title"]
                if "slide_type" in patch:
                    slide.content_type = patch["slide_type"]
                slide.slide_metadata = {**(slide.slide_metadata or {}), **patch}
            if item.slide_index < len(legacy):
                legacy[item.slide_index].update(patch)
            document.update(
                outline=merged, outline_revision=_document_revision("outline", merged)
            )
        outline["updated_at"] = stamp
        outline["content"] = json.dumps(
            {key: value for key, value in outline.items() if key != "content"},
            ensure_ascii=False,
        )
        project.outline, project.slides_data, project.updated_at = (
            outline,
            legacy,
            stamp,
        )
        stage = await self.session.scalar(
            select(TodoStage).where(
                TodoStage.project_id == project_id,
                TodoStage.stage_id == "outline_generation",
            )
        )
        if stage:
            stage.result = {
                **(stage.result or {}),
                "outline_content": outline["content"],
            }
        revision = _project_revision(project)
        await self.session.commit()
        return dict(project_revision=revision, pages=documents, editable=True)
