"""Authenticated, version-checked project card thumbnails."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth.middleware import get_current_user_required
from ...database.database import AsyncSessionLocal
from ...database.models import User
from ...services.project_cover_service import project_cover_service
from ...services.project_cover_source import load_cover_source

router = APIRouter()
NO_STORE = {"Cache-Control": "private, no-store", "Vary": "Cookie, Authorization"}


async def _source(project_id: str, user_id: int):
    async with AsyncSessionLocal() as session:
        return await load_cover_source(session, project_id, user_id)


@router.get("/api/projects/{project_id}/cover")
async def project_cover(
    request: Request,
    project_id: str,
    v: str = "",
    user: User = Depends(get_current_user_required),
):
    source = await _source(project_id, user.id)
    if source is None:
        raise HTTPException(404, "Project not found", headers=NO_STORE)
    if not source.html:
        return Response(status_code=204, headers=NO_STORE)
    if v and v != source.version:
        raise HTTPException(
            409, "Cover content changed; refresh the project list", headers=NO_STORE
        )
    image = await project_cover_service.get_cover(source, str(request.base_url))
    if image is None:
        return Response(status_code=503, headers={**NO_STORE, "Retry-After": "60"})
    # Editing, replacing or deleting during rendering must not deliver an old cover.
    current = await _source(project_id, user.id)
    if current is None:
        raise HTTPException(404, "Project not found", headers=NO_STORE)
    if current.version != source.version:
        raise HTTPException(
            409, "Cover content changed; refresh the project list", headers=NO_STORE
        )
    headers = {
        "Cache-Control": "private, no-cache",
        "Vary": "Cookie, Authorization",
        "ETag": f'"{source.version}.{hashlib.sha256(image).hexdigest()}"',
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    return Response(content=image, media_type="image/webp", headers=headers)
