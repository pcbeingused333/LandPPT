"""Authenticated media previews; never render arbitrary stored content inline."""

import logging
import re
from urllib.parse import quote

from fastapi import HTTPException, Response
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)


class MediaPreviewResponse(StreamingResponse):
    def __init__(self, *args, reader, **kwargs):
        self.reader = reader
        super().__init__(*args, **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Also covers disconnect during response headers, before the body
            # iterator has started and can run its own finally block.
            await self.reader.aclose()


# Require both registered export type and a matching explicit MIME/extension.
# In particular, narration ZIPs, HTML and SVG are not inline media.
FORMATS = {
    ("video/mp4", ".mp4"): ("video", "video/mp4"),
    ("video/webm", ".webm"): ("video", "video/webm"),
    ("audio/mpeg", ".mp3"): ("audio", "audio/mpeg"),
    ("audio/wav", ".wav"): ("audio", "audio/wav"),
    ("audio/x-wav", ".wav"): ("audio", "audio/wav"),
    ("audio/ogg", ".ogg"): ("audio", "audio/ogg"),
    ("audio/ogg", ".oga"): ("audio", "audio/ogg"),
    ("audio/mp4", ".m4a"): ("audio", "audio/mp4"),
    ("audio/webm", ".webm"): ("audio", "audio/webm"),
}


def preview_format(artifact_type, filename, content_type):
    extension = "." + (filename or "").rpartition(".")[2].lower()
    mime = (content_type or "").partition(";")[0].strip().lower()
    result = FORMATS.get((mime, extension))
    if result and artifact_type == f"narration_{result[0]}_export":
        return result
    return None


def byte_range(value, size):
    """Single RFC byte range. Unknown units/multi-ranges are ignored."""
    if not value or not value.startswith("bytes=") or "," in value:
        return None
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value[:129])
    if len(value) > 128 or not match or not any(match.groups()) or not size:
        raise ValueError("Unsatisfiable range")
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if not suffix:
            raise ValueError("Unsatisfiable range")
        return max(0, size - suffix), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable range")
    return start, end


async def preview_response(
    artifact, storage, *, method, range_header=None, if_range=None
):
    format_ = preview_format(
        artifact.artifact_type, artifact.filename, artifact.content_type
    )
    if not format_:
        raise HTTPException(415, "此文件暂不支持在线播放，请下载查看")
    if artifact.storage_backend != storage.backend_name:
        raise HTTPException(503, "文件存储暂不可用，请稍后重试")
    try:
        # Stored bytes are authoritative; metadata size may be missing or stale.
        size = await storage.size(artifact.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "文件已不可用") from None
    except Exception:
        logger.exception("Unable to read media preview size")
        raise HTTPException(503, "文件存储暂不可用，请稍后重试") from None
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Content-Disposition": "inline; filename*=UTF-8''"
        + quote(artifact.filename, safe=""),
    }
    try:
        # No validator is advertised: an If-Range request gets the full entity.
        selected = (
            byte_range(range_header, size) if method == "GET" and not if_range else None
        )
    except ValueError:
        return Response(
            status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"}
        )
    start, end = selected or (0, size - 1)
    headers["Content-Length"] = str(end - start + 1)
    if selected:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    status = 206 if selected else 200
    if method == "HEAD" or not size:
        return Response(status_code=status, media_type=format_[1], headers=headers)

    stream = storage.open_range(artifact.storage_key, start, end)
    try:
        first = await anext(stream)
    except (FileNotFoundError, StopAsyncIteration):
        await stream.aclose()
        raise HTTPException(404, "文件已不可用") from None
    except Exception:
        await stream.aclose()
        logger.exception("Unable to open media preview")
        raise HTTPException(503, "文件存储暂不可用，请稍后重试") from None

    async def chunks():
        try:
            yield first
            async for chunk in stream:
                yield chunk
        finally:
            await stream.aclose()

    return MediaPreviewResponse(
        chunks(),
        status_code=status,
        media_type=format_[1],
        headers=headers,
        reader=stream,
    )
