"""Render saved slides in an isolated, credential-free preview context.

The browser never fetches arbitrary URLs itself. Only bounded public resources,
bundled static assets and the owner's image artifacts can be fulfilled.
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import aiohttp
from PIL import Image

from ..project_cover_source import CoverSource
from .html_render_service import HtmlRenderService

PREVIEW_URL = "https://landppt-cover.invalid/"
MAX_RESOURCE = 8 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
SCRIPT_HOSTS = {
    "cdn.tailwindcss.com",
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "unpkg.com",
}


class PublicResolver(aiohttp.resolver.DefaultResolver):
    async def resolve(self, host, port=0, family=0):
        records = await super().resolve(host, port, family)
        if not records or any(
            not ipaddress.ip_address(row["host"]).is_global for row in records
        ):
            raise OSError("Private resource address")
        return records


def public_resource_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.port not in {None, 80, 443}:
            return False
        try:
            return ipaddress.ip_address(parsed.hostname).is_global
        except ValueError:
            # DNS names are checked again at connection time by PublicResolver.
            return True
    except ValueError:
        return False


class CoverResources:
    def __init__(
        self, source: CoverSource, base_url: str, session: aiohttp.ClientSession
    ):
        self.source = source
        self.session = session
        self.local_hosts = {
            "landppt-cover.invalid",
            "localhost",
            "127.0.0.1",
            urlsplit(base_url).hostname,
        }
        self.total = 0
        self.count = 0
        self.slots = asyncio.Semaphore(4)

    async def read(self, url: str, kind: str) -> tuple[bytes, str] | None:
        if kind not in {"image", "stylesheet", "font", "script"}:
            return None
        self.count += 1
        if self.count > 48:
            return None
        parsed = urlsplit(url)
        async with self.slots:
            if parsed.hostname in self.local_hosts:
                result = await self._local(unquote(parsed.path), kind)
            elif public_resource_url(url) and (
                kind != "script" or parsed.hostname in SCRIPT_HOSTS
            ):
                result = await self._public(url, kind)
            else:
                return None
            if result:
                self.total += len(result[0])
                if len(result[0]) > MAX_RESOURCE or self.total > MAX_TOTAL:
                    return None
            return result

    async def _local(self, path: str, kind: str) -> tuple[bytes, str] | None:
        if path.startswith("/static/"):
            root = Path(__file__).resolve().parents[2] / "web/static"
            target = (root / path.removeprefix("/static/")).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                return None
            if target.stat().st_size > MAX_RESOURCE:
                return None
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return await asyncio.to_thread(target.read_bytes), mime
        prefixes = ("/api/image/view/", "/api/image/thumbnail/")
        prefix = next((item for item in prefixes if path.startswith(item)), None)
        if prefix and kind == "image":
            image_id = path.removeprefix(prefix)
            if not image_id or "/" in image_id:
                return None
            from ..storage import get_artifact_service

            service = get_artifact_service()
            artifact = await service.get_task_artifact(
                image_id, artifact_type="image_cache", user_id=self.source.user_id
            )
            if artifact and (artifact.content_type or "").startswith("image/"):
                chunks, size = [], 0
                async for chunk in service.open_stream(artifact):
                    size += len(chunk)
                    if size > MAX_RESOURCE:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks), artifact.content_type
        return None

    async def _public(self, url: str, kind: str) -> tuple[bytes, str] | None:
        # No cookies, authorization headers, environment proxies or redirects.
        # Revalidate each redirect before resolving/connecting, including scripts.
        for _ in range(4):
            if not public_resource_url(url):
                return None
            if kind == "script" and urlsplit(url).hostname not in SCRIPT_HOSTS:
                return None
            async with self.session.get(url, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        return None
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    return None
                if response.content_length and response.content_length > MAX_RESOURCE:
                    return None
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > MAX_RESOURCE:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get(
                    "Content-Type", "application/octet-stream"
                )
        return None


async def render_project_cover(source: CoverSource, base_url: str) -> bytes:
    # Reuse the installed Chromium and its managed lifecycle, never its export
    # context/cookies. No persistent project HTML or screenshots are exposed.
    browser = await HtmlRenderService().converter._get_or_create_browser()
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        device_scale_factor=1,
        service_workers="block",
        accept_downloads=False,
    )
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(resolver=PublicResolver()),
            timeout=aiohttp.ClientTimeout(total=5),
            cookie_jar=aiohttp.DummyCookieJar(),
            trust_env=False,
        ) as session:
            resources = CoverResources(source, base_url, session)
            page = await context.new_page()
            page.set_default_timeout(10000)
            document_loaded = False

            async def fulfill(route):
                nonlocal document_loaded
                request = route.request
                if (
                    not document_loaded
                    and request.url == PREVIEW_URL
                    and request.is_navigation_request()
                    and request.frame == page.main_frame
                ):
                    document_loaded = True
                    await route.fulfill(
                        body=source.html,
                        content_type="text/html; charset=utf-8",
                        headers={
                            "Content-Security-Policy": (
                                "default-src 'none'; sandbox allow-scripts; "
                                "script-src 'unsafe-inline' 'unsafe-eval' https:; "
                                "style-src 'unsafe-inline' https: http: data:; "
                                "img-src https: http: data:; font-src https: http: data:; "
                                "connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"
                            )
                        },
                    )
                    return
                result = None
                if request.method == "GET" and not request.is_navigation_request():
                    try:
                        result = await resources.read(
                            request.url, request.resource_type
                        )
                    except Exception:
                        pass  # Missing resources are a best-effort preview, never a request escape.
                if result:
                    await route.fulfill(
                        body=result[0],
                        content_type=result[1],
                        headers={"Access-Control-Allow-Origin": "*"},
                    )
                else:
                    await route.abort()

            await context.route("**/*", fulfill)
            await page.goto(PREVIEW_URL, wait_until="networkidle", timeout=15000)
            try:
                await page.wait_for_function(
                    "document.fonts.status === 'loaded' && [...document.images].every(img => img.complete)",
                    timeout=2000,
                )
            except Exception:
                pass
            png = await page.screenshot(type="png", animations="disabled", timeout=5000)
            return await asyncio.to_thread(_thumbnail, png)
    finally:
        await context.close()


def _thumbnail(png: bytes) -> bytes:
    with Image.open(io.BytesIO(png)) as image:
        image = image.convert("RGB").resize((640, 360), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=85)
        return output.getvalue()
