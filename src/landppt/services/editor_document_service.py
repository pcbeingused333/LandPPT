"""Page text editing without rewriting presentation artwork or generation settings."""

import copy
import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from ..database.models import Project, SlideData, SpeechScript, TodoStage


def _revision(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _document_revision(kind, value):
    # Reordering changes positions/timestamps, not the page's editable text.
    ignored = (
        {"slide_index", "updated_at"}
        if kind == "speech"
        else {"slide_index", "page_number"}
    )
    return _revision(
        {key: item for key, item in value.items() if key not in ignored}
        if value is not None
        else None
    )


def _script_payload(script):
    if script is None:
        return None
    return {
        "id": script.id,
        "slide_index": script.slide_index,
        "language": script.language,
        "slide_title": script.slide_title,
        "script_content": script.script_content,
        "estimated_duration": script.estimated_duration,
        "speaker_notes": script.speaker_notes,
        "updated_at": script.updated_at,
    }


def _outline_block(blocks, legacy_slides, slide, index):
    block = blocks[index] if index < len(blocks) else {}
    if block:
        return block
    legacy = legacy_slides[index] if index < len(legacy_slides) else {}
    metadata = (slide.slide_metadata or {}) if slide else legacy
    return {
        "title": slide.title if slide else legacy.get("title", f"第{index + 1}页"),
        "slide_type": (
            slide.content_type if slide else legacy.get("slide_type", "content")
        ),
        "content_points": metadata.get("content_points", []),
        "description": metadata.get("description", ""),
    }


class EditorDocumentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _page(
        self, project_id, user_id, index, language, slide_id, *, lock=False
    ):
        statement = (
            select(Project)
            .where(Project.project_id == project_id, Project.user_id == user_id)
            .options(
                load_only(
                    Project.id,
                    Project.project_id,
                    Project.user_id,
                    Project.outline,
                    Project.updated_at,
                )
            )
        )
        if lock:
            statement = statement.with_for_update()
        project = await self.session.scalar(statement)
        if project is None:
            raise HTTPException(404, "Project not found")
        outline = copy.deepcopy(project.outline or {})
        blocks = outline.get("slides") or []
        slide = await self.session.scalar(
            select(SlideData)
            .where(SlideData.project_id == project_id, SlideData.slide_index == index)
            .options(
                load_only(
                    SlideData.id,
                    SlideData.project_id,
                    SlideData.slide_index,
                    SlideData.slide_id,
                    SlideData.title,
                    SlideData.content_type,
                    SlideData.slide_metadata,
                )
            )
        )
        legacy_slides = []
        if slide is None:
            await self.session.refresh(project, ["slides_data"])
            legacy_slides = project.slides_data or []
        if index < 0 or (
            slide is None and index >= max(len(blocks), len(legacy_slides))
        ):
            raise HTTPException(404, "幻灯片不存在，请刷新页面")
        identity = (
            slide.slide_id
            if slide
            else (
                legacy_slides[index].get("slide_id")
                if index < len(legacy_slides)
                else None
            )
        )
        if slide_id and slide_id != identity:
            raise HTTPException(409, "页面顺序已改变，请刷新后重试；草稿已保留")
        block = _outline_block(blocks, legacy_slides, slide, index)
        script = await self.session.scalar(
            select(SpeechScript)
            .where(
                SpeechScript.project_id == project_id,
                SpeechScript.slide_index == index,
                SpeechScript.language == language,
            )
            .order_by(SpeechScript.updated_at.desc(), SpeechScript.id.desc())
            .limit(1)
        )
        payload = _script_payload(script)
        return (
            project,
            slide,
            outline,
            block,
            script,
            {
                "slide_index": index,
                "slide_id": identity,
                "language": language,
                "outline": block,
                "script": payload,
                "outline_revision": _document_revision("outline", block),
                "speech_revision": _document_revision("speech", payload),
            },
        )

    async def read(self, project_id, user_id, index, language, slide_id=None):
        *_, document = await self._page(project_id, user_id, index, language, slide_id)
        return document

    async def save(self, project_id, user_id, index, language, body):
        project, slide, outline, block, script, document = await self._page(
            project_id, user_id, index, language, body.slide_id, lock=True
        )
        if body.revision != document[f"{body.kind}_revision"]:
            raise HTTPException(
                409, "内容已在其他窗口更新，请重新加载后合并；草稿已保留"
            )

        # The compare-and-swap also protects SQLite, where FOR UPDATE is ignored.
        stamp = time.time()
        result = await self.session.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.user_id == user_id,
                Project.updated_at == project.updated_at,
            )
            .values(updated_at=stamp)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "项目已更新，请重新加载后重试；草稿已保留")

        if body.kind == "outline":
            await self.session.refresh(project, ["slides_data"])
            patch = body.outline.model_dump(exclude_unset=True)
            merged = {**block, **patch}
            if "slide_type" in patch:
                merged["type"] = patch["slide_type"]
            blocks = outline.setdefault("slides", [])
            while len(blocks) <= index:
                blocks.append({})
            blocks[index] = merged
            outline["updated_at"] = stamp
            # Preserve unrecognized fields; keep the legacy serialized view in sync.
            outline["content"] = json.dumps(
                {key: value for key, value in outline.items() if key != "content"},
                ensure_ascii=False,
            )
            project.outline = outline
            metadata = {
                key: merged[key]
                for key in ("title", "slide_type", "content_points", "description")
                if key in merged
            }
            if slide:
                slide.title = merged.get("title", slide.title)
                slide.content_type = merged.get("slide_type", slide.content_type)
                slide.slide_metadata = {**(slide.slide_metadata or {}), **metadata}
            legacy = copy.deepcopy(project.slides_data or [])
            if index < len(legacy):
                legacy[index].update(metadata)
                project.slides_data = legacy
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
            document["outline"] = merged
            document["outline_revision"] = _document_revision("outline", merged)
        else:
            fields = body.speech.model_dump()
            if script is None:
                script = SpeechScript(
                    project_id=project_id,
                    slide_index=index,
                    language=language,
                    generation_type="single",
                    tone="conversational",
                    target_audience="general_public",
                    language_complexity="moderate",
                    speaking_pace="normal",
                    created_at=stamp,
                )
                self.session.add(script)
            for key, value in fields.items():
                setattr(script, key, value)
            script.updated_at = stamp
            await self.session.flush()
            document["script"] = _script_payload(script)
            document["speech_revision"] = _document_revision(
                "speech", document["script"]
            )
        await self.session.commit()
        return document
