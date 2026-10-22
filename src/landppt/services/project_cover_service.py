"""Bounded, private, content-addressed thumbnails; never part of a list request."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable

from .project_cover_source import CoverSource

logger = logging.getLogger(__name__)
CACHE_TTL = 24 * 60 * 60
MAX_CACHE_BYTES = 256 * 1024 * 1024
FAILURE_TTL = 60
RENDER_TIMEOUT = 20
RESPONSE_TIMEOUT = 30


class ProjectCoverService:
    def __init__(
        self,
        cache_dir: Path | None = None,
        renderer: Callable[[CoverSource, str], Awaitable[bytes]] | None = None,
    ) -> None:
        # data is private and persistent in both local and Docker deployments.
        # temp is deliberately avoided: it can be exposed by a static mount.
        self.cache_dir = cache_dir or Path("data/project-covers")
        self.renderer = renderer or self._render
        self._slots = asyncio.Semaphore(2)
        self._pending: dict[Path, asyncio.Task] = {}
        self._failed: dict[Path, float] = {}
        self._last_prune = 0.0

    def _path(self, source: CoverSource) -> Path:
        scope = hashlib.sha256(
            f"{source.user_id}:{source.project_id}".encode()
        ).hexdigest()
        return self.cache_dir / scope / f"{source.version}.webp"

    @staticmethod
    def _fresh(path: Path) -> bool:
        try:
            return (
                path.stat().st_size > 0
                and time.time() - path.stat().st_mtime < CACHE_TTL
            )
        except OSError:
            return False

    async def get_cover(self, source: CoverSource, base_url: str) -> bytes | None:
        if not source.html:
            return None
        path = self._path(source)
        if self._fresh(path):
            try:
                return await asyncio.to_thread(path.read_bytes)
            except OSError:
                pass  # Another worker can prune or replace the cache concurrently.
        if self._failed.get(path, 0) > time.monotonic():
            return None
        task = self._pending.get(path)
        if task is None:
            if len(self._pending) >= 16:
                return None
            task = asyncio.create_task(self._generate(source, path, base_url))
            self._pending[path] = task
            task.add_done_callback(lambda done: self._pending.pop(path, None))
        # A disconnected card must not cancel another viewer's identical request.
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=RESPONSE_TIMEOUT
            )
        except asyncio.TimeoutError:
            return None

    async def _generate(
        self, source: CoverSource, path: Path, base_url: str
    ) -> bytes | None:
        try:
            async with self._slots:
                if self._fresh(path):
                    try:
                        return await asyncio.to_thread(path.read_bytes)
                    except OSError:
                        pass
                image = await asyncio.wait_for(
                    self.renderer(source, base_url), timeout=RENDER_TIMEOUT
                )
                if not image:
                    raise ValueError("Empty cover")
                await asyncio.to_thread(self._store, path, image)
                self._failed.pop(path, None)
                return image
        except Exception as exc:
            logger.warning(
                "Cover unavailable for project %s: %s",
                source.project_id,
                type(exc).__name__,
            )
            now = time.monotonic()
            self._failed = {
                key: until for key, until in self._failed.items() if until > now
            }
            # Bound the failure cache, even if many distinct projects fail.
            if len(self._failed) >= 256:
                self._failed.pop(next(iter(self._failed)))
            self._failed[path] = now + FAILURE_TTL
            return None

    def _store(self, path: Path, image: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(image)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        # Successful replacement retires older content versions of this project.
        for old in path.parent.glob("*.webp"):
            if old != path:
                old.unlink(missing_ok=True)
        if time.monotonic() - self._last_prune > 3600:
            self._last_prune = time.monotonic()
            self._prune(path)

    def _prune(self, keep: Path) -> None:
        entries = []
        for entry in self.cache_dir.glob("*/*.webp"):
            try:
                stat = entry.stat()
                entries.append((stat.st_mtime, stat.st_size, entry))
            except OSError:
                continue
        total = sum(size for _, size, _ in entries)
        for modified, size, entry in sorted(entries):
            if entry == keep:
                continue
            if time.time() - modified >= CACHE_TTL or total > MAX_CACHE_BYTES:
                entry.unlink(missing_ok=True)
                total -= size

    @staticmethod
    async def _render(source: CoverSource, base_url: str) -> bytes:
        from .export_infra.project_cover_renderer import render_project_cover

        return await render_project_cover(source, base_url)


project_cover_service = ProjectCoverService()
