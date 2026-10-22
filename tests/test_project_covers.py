"""Owner isolation, content invalidation and bounded cover rendering."""

import asyncio
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from landppt.database.models import Base, Project, SlideData, User
from landppt.services.project_cover_service import CACHE_TTL, ProjectCoverService
from landppt.services.project_cover_source import (
    CoverSource,
    load_cover_source,
    project_cover_url,
)


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def scalar(self, query):
        return self.session.scalar(query)

    async def execute(self, query):
        return self.session.execute(query)


@pytest.fixture
def cover_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [User(id=i, username=f"user-{i}", password_hash="fixture") for i in (1, 2)]
        )
        session.add(
            Project(
                project_id="owned",
                user_id=1,
                title="Title",
                topic="Topic",
                scenario="general",
                slides_data=[{"html_content": "stale JSON"}],
            )
        )
        session.add(
            Project(
                project_id="legacy",
                user_id=2,
                title="Legacy",
                topic="Topic",
                scenario="general",
                slides_data=[
                    {"html_content": "legacy first"},
                    {"html_content": "second"},
                ],
            )
        )
        session.add_all(
            [
                SlideData(
                    project_id="owned",
                    slide_index=index,
                    slide_id=f"slide-{index}",
                    title="Page",
                    content_type="title",
                    html_content=html,
                )
                for index, html in [(2, "second"), (0, "real first")]
            ]
        )
        session.commit()
        yield AsyncSessionAdapter(session)
    engine.dispose()


@pytest.mark.asyncio
async def test_source_uses_first_ordered_row_and_never_crosses_ownership(cover_db):
    source = await load_cover_source(cover_db, "owned", 1)
    assert source.html == "real first"
    assert await load_cover_source(cover_db, "owned", 2) is None
    assert await load_cover_source(cover_db, "missing", 1) is None
    assert (await load_cover_source(cover_db, "legacy", 2)).html == "legacy first"
    assert project_cover_url("owned", [{"html_content": source.html}]).endswith(
        source.version
    )


@pytest.mark.asyncio
async def test_summary_and_endpoint_share_identity_and_empty_first_page_stays_empty(
    cover_db,
):
    from landppt.database.service import DatabaseService

    project = await DatabaseService(cover_db).get_project("owned", user_id=1)
    source = await load_cover_source(cover_db, "owned", 1)
    assert project.cover_url == project_cover_url(
        "owned", [{"html_content": source.html}]
    )
    cover_db.session.query(SlideData).filter(SlideData.slide_index == 0).update(
        {"html_content": ""}
    )
    cover_db.session.commit()
    assert not (await load_cover_source(cover_db, "owned", 1)).html
    assert (
        project_cover_url("owned", [{"html_content": "", "generation_failed": True}])
        is None
    )


@pytest.mark.asyncio
async def test_cache_hits_content_changes_owner_scope_expiry_and_restart(tmp_path):
    render = AsyncMock(return_value=b"webp bytes")
    service = ProjectCoverService(tmp_path, render)
    source = CoverSource("project", 1, "first page")
    assert await service.get_cover(source, "http://app") == b"webp bytes"
    assert await service.get_cover(source, "http://app") == b"webp bytes"
    assert render.await_count == 1
    restarted = ProjectCoverService(tmp_path, render)
    await restarted.get_cover(source, "http://app")
    assert render.await_count == 1
    changed = CoverSource("project", 1, "edited first page")
    await service.get_cover(changed, "http://app")
    assert render.await_count == 2
    assert not service._path(source).exists()
    await service.get_cover(CoverSource("project", 2, changed.html), "http://app")
    assert render.await_count == 3
    path = service._path(changed)
    os.utime(path, (time.time() - CACHE_TTL - 1,) * 2)
    await service.get_cover(changed, "http://app")
    assert render.await_count == 4
    assert not list(tmp_path.glob("*/*.tmp"))


@pytest.mark.asyncio
async def test_failure_cools_down_but_new_content_and_retry_can_recover(tmp_path):
    render = AsyncMock(
        side_effect=[RuntimeError("unavailable"), b"recovered", b"retry"]
    )
    service = ProjectCoverService(tmp_path, render)
    source = CoverSource("project", 1, "old")
    assert await service.get_cover(source, "http://app") is None
    assert await service.get_cover(source, "http://app") is None
    assert render.await_count == 1
    assert (
        await service.get_cover(CoverSource("project", 1, "new"), "http://app")
        == b"recovered"
    )
    service._failed[service._path(source)] = 0
    assert await service.get_cover(source, "http://app") == b"retry"
    assert await service.get_cover(CoverSource("project", 1, ""), "http://app") is None


@pytest.mark.asyncio
async def test_identical_requests_coalesce_and_render_concurrency_is_bounded(tmp_path):
    active, peak, calls = 0, 0, 0

    async def render(source, base_url):
        nonlocal active, peak, calls
        active += 1
        calls += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return b"cover"

    service = ProjectCoverService(tmp_path, render)
    sources = [CoverSource(str(i), 1, "html") for i in range(6)]
    results = await asyncio.gather(
        *(service.get_cover(source, "http://app") for source in sources * 2)
    )
    assert all(result == b"cover" for result in results)
    assert calls == 6 and peak == 2


@pytest.mark.asyncio
async def test_disconnecting_request_does_not_cancel_shared_render(tmp_path):
    started, finish = asyncio.Event(), asyncio.Event()

    async def render(source, base_url):
        started.set()
        await finish.wait()
        return b"cover"

    service = ProjectCoverService(tmp_path, render)
    source = CoverSource("project", 1, "html")
    first = asyncio.create_task(service.get_cover(source, "http://app"))
    await started.wait()
    second = asyncio.create_task(service.get_cover(source, "http://app"))
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    finish.set()
    assert await second == b"cover"


@pytest.mark.asyncio
async def test_render_timeout_falls_back_and_retired_cache_is_pruned(
    tmp_path, monkeypatch
):
    from landppt.services import project_cover_service as module

    monkeypatch.setattr(module, "RENDER_TIMEOUT", 0.01)

    async def slow(source, base_url):
        await asyncio.sleep(10)

    service = ProjectCoverService(tmp_path, slow)
    assert await service.get_cover(CoverSource("slow", 1, "html"), "http://app") is None
    old = tmp_path / "expired" / "old.webp"
    old.parent.mkdir()
    old.write_bytes(b"expired")
    os.utime(old, (time.time() - CACHE_TTL - 1,) * 2)
    service.renderer = AsyncMock(return_value=b"ready")
    assert (
        await service.get_cover(CoverSource("ready", 1, "html"), "http://app")
        == b"ready"
    )
    assert not old.exists()


@pytest.mark.asyncio
async def test_cover_endpoint_checks_owner_version_and_cache_on_every_request(
    monkeypatch,
):
    from landppt.auth.middleware import get_current_user_required
    from landppt.web.route_modules import project_cover_routes as routes

    source = CoverSource("project", 1, "html")
    state = {"source": source}

    async def current(project_id, user_id):
        return state["source"] if project_id == "project" and user_id == 1 else None

    def user(request: Request):
        if "x-test-user" not in request.headers:
            raise HTTPException(401)
        return SimpleNamespace(id=int(request.headers["x-test-user"]))

    render = AsyncMock(return_value=b"webp")
    monkeypatch.setattr(routes, "_source", current)
    monkeypatch.setattr(
        routes, "project_cover_service", SimpleNamespace(get_cover=render)
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user_required] = user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app"
    ) as client:
        url = f"/api/projects/project/cover?v={source.version}"
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers={"x-test-user": "2"})).status_code == 404
        assert not render.called
        headers = {"x-test-user": "1"}
        response = await client.get(url, headers=headers)
        assert response.status_code == 200 and response.content == b"webp"
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["cache-control"] == "private, no-cache"
        etag = response.headers["etag"]
        assert (
            await client.get(url, headers={**headers, "If-None-Match": etag})
        ).status_code == 304
        assert (
            await client.get(url, headers={"x-test-user": "2", "If-None-Match": etag})
        ).status_code == 404
        render.return_value = b"refreshed image resource"
        refreshed = await client.get(url, headers={**headers, "If-None-Match": etag})
        assert refreshed.status_code == 200 and refreshed.headers["etag"] != etag
        state["source"] = CoverSource("project", 1, "edited")
        assert (await client.get(url, headers=headers)).status_code == 409
        state["source"] = CoverSource("project", 1, "")
        assert (
            await client.get("/api/projects/project/cover", headers=headers)
        ).status_code == 204
        state["source"] = source
        render.return_value = None
        failed = await client.get(url, headers=headers)
        assert failed.status_code == 503 and failed.headers["retry-after"] == "60"
        state["source"] = None
        assert (await client.get(url, headers=headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", [None, CoverSource("project", 1, "edited while rendering")]
)
async def test_deleted_or_changed_content_is_rechecked_after_render(
    monkeypatch, change
):
    from landppt.auth.middleware import get_current_user_required
    from landppt.web.route_modules import project_cover_routes as routes

    source = CoverSource("project", 1, "html")
    monkeypatch.setattr(routes, "_source", AsyncMock(side_effect=[source, change]))
    monkeypatch.setattr(
        routes,
        "project_cover_service",
        SimpleNamespace(get_cover=AsyncMock(return_value=b"old")),
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app"
    ) as client:
        response = await client.get("/api/projects/project/cover")
    assert response.status_code == (404 if change is None else 409)
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://169.254.169.254/latest",
        "http://[::1]/",
        "file:///etc/passwd",
        "https://user:password@example.com/",
        "https://example.com:8000/",
        "http://10.0.0.1/",
        "http://100.64.0.1/",
    ],
)
def test_renderer_rejects_private_and_credentialed_resource_urls(url):
    from landppt.services.export_infra.project_cover_renderer import public_resource_url

    assert not public_resource_url(url)


@pytest.mark.asyncio
async def test_public_dns_is_checked_at_connection_time(monkeypatch):
    import aiohttp
    from landppt.services.export_infra.project_cover_renderer import PublicResolver

    monkeypatch.setattr(
        aiohttp.resolver.DefaultResolver,
        "resolve",
        AsyncMock(return_value=[{"host": "127.0.0.1"}]),
    )
    resolver = PublicResolver()
    try:
        with pytest.raises(OSError):
            await resolver.resolve("rebinding.example")
    finally:
        await resolver.close()


@pytest.mark.asyncio
async def test_local_resources_reject_traversal_and_scope_image_artifacts(monkeypatch):
    from landppt.services import storage
    from landppt.services.export_infra.project_cover_renderer import CoverResources

    artifacts = SimpleNamespace(get_task_artifact=AsyncMock(return_value=None))
    monkeypatch.setattr(storage, "get_artifact_service", lambda: artifacts)
    resources = CoverResources(CoverSource("project", 7, "html"), "http://app", None)
    assert (
        await resources.read(
            "https://landppt-cover.invalid/static/../../../../.env", "stylesheet"
        )
        is None
    )
    assert (
        await resources.read(
            "https://landppt-cover.invalid/api/image/view/other", "image"
        )
        is None
    )
    artifacts.get_task_artifact.assert_awaited_once_with(
        "other", artifact_type="image_cache", user_id=7
    )
    assert await resources.read("http://127.0.0.1/admin", "document") is None


@pytest.mark.asyncio
async def test_public_redirect_cannot_escape_to_private_network():
    from landppt.services.export_infra.project_cover_renderer import CoverResources

    class Response:
        status = 302
        headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Session:
        urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            return Response()

    session = Session()
    resources = CoverResources(CoverSource("project", 1, "html"), "http://app", session)
    assert await resources.read("https://images.example/cover.png", "image") is None
    assert session.urls == ["https://images.example/cover.png"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["html", "svg"])
async def test_real_renderer_preserves_canvas_and_inline_content_without_private_requests(
    monkeypatch, mode
):
    import io

    from PIL import Image

    from landppt.services.export_infra import project_cover_renderer as renderer
    from landppt.services.pyppeteer_pdf_converter import PlaywrightPDFConverter

    pytest.importorskip("playwright.async_api")
    converter = PlaywrightPDFConverter()
    monkeypatch.setattr(
        renderer, "HtmlRenderService", lambda: SimpleNamespace(converter=converter)
    )
    external = AsyncMock(side_effect=AssertionError("Unexpected external request"))
    monkeypatch.setattr(renderer.CoverResources, "_public", external)
    if mode == "html":
        html = """<html><body style="margin:0;width:1280px;height:720px">
          <script>document.body.style.background='#123456'; fetch('http://127.0.0.1/admin', {method:'POST'}).catch(()=>{}); window.open('http://127.0.0.1/admin');</script>
          <img src="http://127.0.0.1/private"><iframe src="http://127.0.0.1/admin"></iframe>
        </body></html>"""
    else:
        html = """<html><body style="margin:0"><svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#123456"/></svg></body></html>"""
    try:
        image = await renderer.render_project_cover(
            CoverSource("project", 1, html), "http://app"
        )
        with Image.open(io.BytesIO(image)) as thumbnail:
            assert thumbnail.format == "WEBP" and thumbnail.size == (640, 360)
            pixel = thumbnail.convert("RGB").getpixel((400, 200))
            assert all(
                abs(actual - expected) < 8
                for actual, expected in zip(pixel, (18, 52, 86))
            )
        assert not external.called
    finally:
        await converter.close()
