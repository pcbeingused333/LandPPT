"""Owner-scoped catalogue of stored, unexpired export artifacts."""

import math
import time
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select

from ..database.models import Artifact, Project
from .artifact_preview_service import preview_format

CATEGORIES = {
    "pdf": ("pdf_export", "PDF"),
    "pptx": ("pptx_export", "PPTX"),
    "audio": ("narration_audio_export", "讲解音频"),
    "video": ("narration_video_export", "讲解视频"),
}
TYPE_CATEGORIES = {value[0]: (key, value[1]) for key, value in CATEGORIES.items()}


def personal_file_conditions(user_id):
    return [
        Artifact.user_id == user_id,
        Artifact.artifact_type.in_(TYPE_CATEGORIES),
        or_(Artifact.expires_at.is_(None), Artifact.expires_at > time.time()),
        or_(Artifact.project_id.is_(None), Project.user_id == user_id),
    ]


class ArtifactLibraryService:
    def __init__(self, session):
        self.session = session

    async def preview_artifact(self, user_id, artifact_id):
        artifact = await self.session.scalar(
            select(Artifact)
            .outerjoin(Project, Artifact.project_id == Project.project_id)
            .where(Artifact.id == artifact_id, *personal_file_conditions(user_id))
        )
        if artifact is None:
            raise HTTPException(404, "文件不存在或无权访问")
        return artifact

    async def list_files(
        self,
        user_id,
        *,
        page=1,
        per_page=20,
        category="",
        search="",
        sort="newest",
        project_id=None,
    ):
        project_filter = None
        if project_id:
            row = (
                await self.session.execute(
                    select(Project.project_id, Project.title, Project.topic).where(
                        Project.project_id == project_id, Project.user_id == user_id
                    )
                )
            ).first()
            if row is None:
                raise HTTPException(404, "项目不存在或无权访问")
            project_filter = {
                "id": row.project_id,
                "title": row.title or row.topic or "未命名项目",
            }
        conditions = personal_file_conditions(user_id)
        if category:
            conditions.append(Artifact.artifact_type == CATEGORIES[category][0])
        if project_id:
            conditions.append(Artifact.project_id == project_id)
        search = search.strip()
        if search:
            escaped = (
                search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    Artifact.filename.ilike(pattern, escape="\\"),
                    Project.title.ilike(pattern, escape="\\"),
                    Project.topic.ilike(pattern, escape="\\"),
                )
            )
        join = Artifact.project_id == Project.project_id
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Artifact)
                .outerjoin(Project, join)
                .where(*conditions)
            )
            or 0
        )
        page = min(page, max(1, math.ceil(total / per_page)))
        order = [Artifact.created_at.desc(), Artifact.id.desc()]
        if sort == "oldest":
            order = [Artifact.created_at.asc(), Artifact.id.asc()]
        elif sort == "largest":
            order = [
                case((Artifact.size_bytes.is_(None), 1), else_=0),
                Artifact.size_bytes.desc(),
                *order,
            ]
        rows = (
            await self.session.execute(
                select(
                    Artifact.id,
                    Artifact.filename,
                    Artifact.artifact_type,
                    Artifact.content_type,
                    Artifact.size_bytes,
                    Artifact.created_at,
                    Artifact.expires_at,
                    Project.project_id,
                    Project.title,
                    Project.topic,
                )
                .select_from(Artifact)
                .outerjoin(Project, join)
                .where(*conditions)
                .order_by(*order)
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        ).all()
        files = []
        for row in rows:
            kind, label = TYPE_CATEGORIES[row.artifact_type]
            media = preview_format(row.artifact_type, row.filename, row.content_type)
            files.append(
                {
                    "id": row.id,
                    "filename": row.filename,
                    "category": kind,
                    "category_label": label,
                    "file_size": row.size_bytes,
                    "created_at": row.created_at,
                    "expires_at": row.expires_at,
                    "project": (
                        {
                            "id": row.project_id,
                            "title": row.title or row.topic or "未命名项目",
                        }
                        if row.project_id
                        else None
                    ),
                    "download_url": f"/api/artifacts/{quote(row.id, safe='')}/download",
                    "preview_kind": media[0] if media else None,
                }
            )
        return {
            "files": files,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_count": total,
            },
            "project": project_filter,
        }
