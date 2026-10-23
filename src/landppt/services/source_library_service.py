"""Personal source catalogue, projected and paged by project before JSON reads."""

import math
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import func, select

from ..database.models import Project
from .project_source_service import source_files


def safe_source_url(value):
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(char in parsed.netloc for char in "<>\\")
        ):
            return None
        parsed.port
    except ValueError:
        return None
    return value


class SourceLibraryService:
    def __init__(self, session):
        self.session = session

    async def list_projects(
        self,
        user_id,
        *,
        page=1,
        per_page=6,
        search="",
        kind="",
        sort="newest",
        project_id=None,
    ):
        project_filter = None
        if project_id:
            project = (
                await self.session.execute(
                    select(Project.project_id, Project.title, Project.topic).where(
                        Project.project_id == project_id, Project.user_id == user_id
                    )
                )
            ).first()
            if project is None:
                raise HTTPException(404, "项目不存在或无权访问")
            project_filter = {
                "id": project.project_id,
                "title": project.title or project.topic or "未命名项目",
            }
        requirements = Project.confirmed_requirements
        mode = requirements["content_source"].as_string()
        conditions = [Project.user_id == user_id]
        if project_id:
            conditions.append(Project.project_id == project_id)
        else:
            conditions.append(mode.in_(["file", "url", "mixed"]))
        if kind:
            conditions.append(mode.in_([kind, "mixed"]))
        search = search.strip()
        if search:
            pattern = (
                "%"
                + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            conditions.append(
                Project.title.ilike(pattern, escape="\\")
                | Project.topic.ilike(pattern, escape="\\")
            )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(Project).where(*conditions)
            )
            or 0
        )
        page = min(page, max(1, math.ceil(total / per_page)))
        order = [Project.updated_at.desc(), Project.project_id.desc()]
        if sort == "oldest":
            order = [Project.updated_at.asc(), Project.project_id.asc()]
        # Select only source fields; never load outline, slides or generated
        # source material/AI settings embedded in confirmed_requirements.
        rows = (
            await self.session.execute(
                select(
                    Project.project_id,
                    Project.title,
                    Project.topic,
                    Project.updated_at,
                    mode.label("mode"),
                    requirements["uploaded_files"].as_json().label("uploads"),
                    requirements["file_path"]
                    .as_string()
                    .is_not(None)
                    .label("legacy_file"),
                    requirements["filename"].as_string().label("legacy_name"),
                    requirements["source_urls"].as_json().label("urls"),
                )
                .where(*conditions)
                .order_by(*order)
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        ).all()
        projects = []
        for row in rows:
            sources = source_files(
                {
                    "content_source": row.mode,
                    "uploaded_files": (
                        row.uploads if isinstance(row.uploads, list) else []
                    ),
                    "file_path": "legacy" if row.legacy_file else None,
                    "filename": row.legacy_name,
                }
            )
            names = []
            for source in sources:
                name = source.get("filename")
                names.append(
                    name.replace("\\", "/").rsplit("/", 1)[-1] or "附件"
                    if isinstance(name, str)
                    else "附件"
                )
            values = row.urls if isinstance(row.urls, list) else []
            urls = [url for value in values if (url := safe_source_url(value))]
            projects.append(
                {
                    "id": row.project_id,
                    "title": row.title or row.topic or "未命名项目",
                    "updated_at": row.updated_at,
                    "source_kind": (
                        row.mode if row.mode in {"file", "url", "mixed"} else "manual"
                    ),
                    "files": names[:50],
                    "file_count": len(names),
                    "urls": urls[:50],
                    "url_count": len(values),
                    "invalid_url_count": len(values) - len(urls),
                }
            )
        return {
            "projects": projects,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_count": total,
            },
            "project": project_filter,
        }
