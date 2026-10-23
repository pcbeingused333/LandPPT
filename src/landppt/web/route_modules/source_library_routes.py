"""Read-only personal source index; editing uses the existing source route."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from ...auth.middleware import get_current_user_required
from ...database.database import AsyncSessionLocal
from ...database.models import User
from ...services.source_library_service import SourceLibraryService

router = APIRouter()


@router.get("/api/source-library")
async def source_library(
    response: Response,
    page: int = Query(default=1, ge=1, le=1000000),
    per_page: int = Query(default=6, ge=1, le=20),
    search: str = Query(default="", max_length=200),
    kind: Literal["", "file", "url"] = "",
    sort: Literal["newest", "oldest"] = "newest",
    project_id: str | None = Query(default=None, min_length=1, max_length=100),
    user: User = Depends(get_current_user_required),
):
    response.headers["Cache-Control"] = "no-store"
    async with AsyncSessionLocal() as session:
        result = await SourceLibraryService(session).list_projects(
            user.id,
            page=page,
            per_page=per_page,
            search=search,
            kind=kind,
            sort=sort,
            project_id=project_id,
        )
    return {"success": True, **result}
