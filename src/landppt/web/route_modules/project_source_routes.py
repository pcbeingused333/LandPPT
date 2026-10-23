"""Read and replace source selections without generating or rewriting pages."""

import asyncio
import json
import re
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select

from ...auth.middleware import get_current_user_required
from ...database.database import AsyncSessionLocal
from ...database.models import Project, User
from ...services.project_source_service import ProjectSourceService
from ...utils.thread_pool import run_blocking_io
from .outline_support import (
    _cleanup_project_file_sync,
    _save_uploaded_files_for_confirmed_requirements,
)

router = APIRouter()


def _selection(retained_files, content_urls):
    try:
        retained = json.loads(retained_files)
    except ValueError:
        raise HTTPException(422, "附件选择格式无效")
    if (
        not isinstance(retained, list)
        or len(retained) > 50
        or any(not isinstance(item, str) for item in retained)
        or len(set(retained)) != len(retained)
    ):
        raise HTTPException(422, "附件选择格式无效")
    urls = []
    for value in filter(None, re.split(r"[\s,;]+", content_urls.strip())):
        if "://" in value and not re.match(r"https?://", value, re.I):
            raise HTTPException(422, "请输入有效的 HTTP 或 HTTPS 链接")
        value = value if re.match(r"https?://", value, re.I) else "https://" + value
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or any(char in parsed.netloc for char in "<>\\")
            ):
                raise ValueError()
            parsed.port  # Validate malformed ports too.
        except ValueError:
            raise HTTPException(422, "请输入有效的 HTTP 或 HTTPS 链接")
        normalized = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path or "/",
                parsed.query,
                parsed.fragment,
            )
        )
        if normalized not in urls:
            urls.append(normalized)
    if len(urls) > 50:
        raise HTTPException(422, "最多添加 50 个链接")
    return retained, urls


@router.get("/projects/{project_id}/sources")
async def read_sources(
    project_id: str, response: Response, user: User = Depends(get_current_user_required)
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        sources = await ProjectSourceService(session).read(project_id, user.id)
    return {"success": True, "sources": sources}


@router.post("/projects/{project_id}/sources")
async def replace_sources(
    project_id: str,
    response: Response,
    revision: Annotated[str, Form(min_length=64, max_length=64)],
    retained_files: Annotated[str, Form(max_length=5000)] = "[]",
    content_urls: Annotated[str, Form(max_length=100000)] = "",
    file_upload: Annotated[list[UploadFile] | None, File()] = None,
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    retained, urls = _selection(retained_files, content_urls)
    if len(retained) + len(file_upload or []) > 50:
        raise HTTPException(422, "最多保留 50 个附件")
    # Check ownership/conflicts before saving bytes, then recheck in a fresh
    # transaction after the upload. Clients never provide server file paths.
    async with AsyncSessionLocal() as session:
        await ProjectSourceService(session).check(
            project_id, user.id, revision, retained
        )
    uploaded, committed = [], False
    try:
        if file_upload:
            try:
                metadata = await _save_uploaded_files_for_confirmed_requirements(
                    file_upload
                )
                uploaded = metadata["uploaded_files"]
            except Exception as exc:
                raise HTTPException(422, str(exc)) from exc
        async with AsyncSessionLocal() as session:
            sources = await ProjectSourceService(session).replace(
                project_id, user.id, revision, retained, uploaded, urls
            )
            committed = True
        return {"success": True, "sources": sources}
    finally:
        if not committed:

            async def cleanup():
                # A disconnect can arrive just after COMMIT reached the DB.
                # Never delete files already referenced by a successful save.
                async with AsyncSessionLocal() as session:
                    requirements = await session.scalar(
                        select(Project.confirmed_requirements).where(
                            Project.project_id == project_id, Project.user_id == user.id
                        )
                    )
                referenced = {
                    item.get("file_path")
                    for item in (requirements or {}).get("uploaded_files", [])
                }
                for item in uploaded:
                    if item["file_path"] not in referenced:
                        await run_blocking_io(
                            _cleanup_project_file_sync, item["file_path"]
                        )

            await asyncio.shield(cleanup())
