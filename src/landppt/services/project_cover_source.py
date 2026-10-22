"""Read-only cover identity shared by project summaries and the image endpoint."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from sqlalchemy import select

from ..database.models import Project, SlideData

# Bump when the rendering policy or output geometry changes.
COVER_SCHEMA = "cover-1"


def first_slide_html(slides: list[dict[str, Any]] | None) -> str:
    if not slides or not isinstance(slides[0], dict):
        return ""
    slide = slides[0]
    metadata = slide.get("metadata") or slide.get("slide_metadata") or {}
    if slide.get("generation_failed") or (
        isinstance(metadata, dict) and metadata.get("generation_failed")
    ):
        return ""
    html = slide.get("html_content")
    return html.strip() if isinstance(html, str) else ""


def cover_version(html: str) -> str:
    return hashlib.sha256(f"{COVER_SCHEMA}\0{html}".encode()).hexdigest()


def project_cover_url(
    project_id: str, slides: list[dict[str, Any]] | None
) -> str | None:
    html = first_slide_html(slides)
    if not html:
        return None
    return f"/api/projects/{quote(project_id, safe='')}/cover?v={cover_version(html)}"


@dataclass(frozen=True)
class CoverSource:
    project_id: str
    user_id: int
    html: str

    @property
    def version(self) -> str:
        return cover_version(self.html)


async def load_cover_source(
    session, project_id: str, user_id: int
) -> CoverSource | None:
    """Check ownership before loading just the first slide, without deck/versions."""
    owned = await session.scalar(
        select(Project.id).where(
            Project.project_id == project_id, Project.user_id == user_id
        )
    )
    if owned is None:
        return None
    result = await session.execute(
        select(SlideData.html_content, SlideData.slide_metadata)
        .where(SlideData.project_id == project_id)
        .order_by(SlideData.slide_index, SlideData.id)
        .limit(1)
    )
    row = result.first()
    if row is not None:
        slides = [{"html_content": row.html_content, "metadata": row.slide_metadata}]
    else:
        # Historical projects can still store individual pages in the JSON column.
        slides = await session.scalar(
            select(Project.slides_data).where(
                Project.project_id == project_id, Project.user_id == user_id
            )
        )
    return CoverSource(project_id, user_id, first_slide_html(slides))
