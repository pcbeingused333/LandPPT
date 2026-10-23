"""Personal catalogue and media previews; attachment downloads remain unchanged."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ...auth.middleware import get_current_user_required
from ...database.database import AsyncSessionLocal
from ...database.models import User
from ...services.artifact_library_service import ArtifactLibraryService
from ...services.artifact_preview_service import preview_response
from ...services.storage.factory import get_artifact_storage

router = APIRouter()


@router.get("/api/artifact-library")
async def artifact_library(
    response: Response,
    page: int = Query(default=1, ge=1, le=1000000),
    per_page: int = Query(default=20, ge=1, le=100),
    category: Literal["", "pdf", "pptx", "audio", "video"] = "",
    search: str = Query(default="", max_length=200),
    sort: Literal["newest", "oldest", "largest"] = "newest",
    project_id: str | None = Query(default=None, min_length=1, max_length=100),
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        result = await ArtifactLibraryService(session).list_files(
            user.id,
            page=page,
            per_page=per_page,
            category=category,
            search=search,
            sort=sort,
            project_id=project_id,
        )
    return {"success": True, **result}


@router.api_route(
    "/api/artifact-library/{artifact_id}/preview", methods=["GET", "HEAD"]
)
async def preview_media(
    artifact_id: str, request: Request, user: User = Depends(get_current_user_required)
):
    try:
        async with AsyncSessionLocal() as session:
            artifact = await ArtifactLibraryService(session).preview_artifact(
                user.id, artifact_id
            )
        return await preview_response(
            artifact,
            get_artifact_storage(),
            method=request.method,
            range_header=request.headers.get("range"),
            if_range=request.headers.get("if-range"),
        )
    except HTTPException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise
