"""Private media reads, actual stored ranges and local/S3 stream lifetimes."""

import io
from types import SimpleNamespace

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError
from sqlalchemy import select
from starlette.requests import ClientDisconnect

from landppt.database.models import Artifact
from landppt.services.artifact_preview_service import preview_format, preview_response
from landppt.services.storage.local_storage import LocalArtifactStorage
from landppt.services.storage.s3_storage import S3ArtifactStorage
from landppt.web.route_modules import artifact_library_routes as routes
from test_artifact_library import library  # noqa: F401

PAYLOAD = bytes(range(256)) * 3000


@pytest_asyncio.fixture
async def media(library, tmp_path, monkeypatch):
    class TrackedStorage(LocalArtifactStorage):
        def __init__(self):
            super().__init__(str(tmp_path / "objects"))
            self.stats, self.reads, self.closed = [], [], 0

        async def size(self, key):
            self.stats.append(key)
            return await super().size(key)

        async def open_range(self, key, start, end):
            self.reads.append((key, start, end))
            try:
                async for chunk in super().open_range(key, start, end):
                    yield chunk
            finally:
                self.closed += 1

    storage = TrackedStorage()
    monkeypatch.setattr(routes, "get_artifact_storage", lambda: storage)
    await storage.put_bytes(PAYLOAD, "owned-video")
    await storage.put_bytes(b"", "empty-audio")
    async with library.factory() as session:
        for identifier, values in {
            "playable": {},
            "missing-object": {"storage_key": "missing"},
            "backend-mismatch": {"storage_backend": "s3"},
            "empty": {"storage_key": "empty-audio"},
            "playable-audio": {
                "artifact_type": "narration_audio_export",
                "filename": "讲解.WAV",
                "content_type": "audio/x-wav; charset=binary",
            },
        }.items():
            fields = dict(
                id=identifier,
                user_id=7,
                project_id="mine",
                artifact_type="narration_video_export",
                storage_backend="local",
                storage_key="owned-video",
                filename="讲解.mp4",
                content_type="video/mp4",
                size_bytes=2,
            )
            fields.update(values)
            session.add(Artifact(**fields))
        await session.commit()
    library.storage = storage
    return library


@pytest.mark.asyncio
async def test_catalogue_exposes_only_a_safe_media_kind(media):
    data = (
        await media.client.get("/api/artifact-library", params={"per_page": 100})
    ).json()
    files = {row["id"]: row for row in data["files"]}
    assert files["playable"]["preview_kind"] == "video"
    assert files["playable-audio"]["preview_kind"] == "audio"
    assert files["audio"]["preview_kind"] is None  # Existing ZIP/PDF MIME fixture.
    assert files["pdf-00"]["preview_kind"] is None
    assert not media.storage.stats and not media.storage.reads


@pytest.mark.parametrize(
    "identifier",
    [
        "expired",
        "internal",
        "unsupported",
        "other-owner",
        "mismatched-project",
        "missing-project",
        "absent",
    ],
)
@pytest.mark.asyncio
async def test_preview_never_bypasses_personal_visibility_even_for_admin(
    media, identifier
):
    media.user.is_admin = True
    for method in ["GET", "HEAD"]:
        response = await media.client.request(
            method, f"/api/artifact-library/{identifier}/preview"
        )
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
        assert "PRIVATE" not in response.text and "不得泄漏" not in response.text
    assert not media.storage.stats and not media.storage.reads


@pytest.mark.parametrize(
    "identifier,status",
    [
        ("audio", 415),
        ("pdf-00", 415),
        ("pptx", 415),
        ("video", 415),
        ("backend-mismatch", 503),
        ("missing-object", 404),
    ],
)
@pytest.mark.asyncio
async def test_unplayable_and_unavailable_files_fail_before_streaming(
    media, identifier, status
):
    response = await media.client.get(f"/api/artifact-library/{identifier}/preview")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert not media.storage.reads


@pytest.mark.parametrize(
    "header,start,end,status",
    [
        (None, 0, len(PAYLOAD) - 1, 200),
        ("bytes=5-20", 5, 20, 206),
        ("bytes=100-", 100, len(PAYLOAD) - 1, 206),
        ("bytes=-17", len(PAYLOAD) - 17, len(PAYLOAD) - 1, 206),
        ("bytes=767995-9999999", 767995, len(PAYLOAD) - 1, 206),
        ("bytes=-9999999", 0, len(PAYLOAD) - 1, 206),
        ("items=1-2", 0, len(PAYLOAD) - 1, 200),
        ("bytes=1-2,4-5", 0, len(PAYLOAD) - 1, 200),
    ],
)
@pytest.mark.asyncio
async def test_actual_ranges_and_sizes_are_streamed_without_metadata_trust(
    media, header, start, end, status
):
    response = await media.client.get(
        "/api/artifact-library/playable/preview",
        headers={"Range": header} if header else {},
    )
    assert response.status_code == status
    assert response.content == PAYLOAD[start : end + 1]
    assert response.headers["content-length"] == str(end - start + 1)
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert (
        response.headers["content-disposition"]
        == "inline; filename*=UTF-8''%E8%AE%B2%E8%A7%A3.mp4"
    )
    assert response.headers.get("content-range") == (
        f"bytes {start}-{end}/{len(PAYLOAD)}" if status == 206 else None
    )
    assert (
        media.storage.reads == [("owned-video", start, end)]
        and media.storage.closed == 1
    )


@pytest.mark.parametrize(
    "header",
    [
        "bytes=9999999-",
        "bytes=20-10",
        "bytes=-0",
        "bytes=-",
        "bytes=abc-2",
        "bytes=1-2junk",
        "bytes=" + "9" * 130 + "-",
    ],
)
@pytest.mark.asyncio
async def test_unsatisfiable_ranges_do_not_open_a_stream(media, header):
    response = await media.client.get(
        "/api/artifact-library/playable/preview", headers={"Range": header}
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(PAYLOAD)}"
    assert not response.content and not media.storage.reads


@pytest.mark.asyncio
async def test_head_if_range_and_empty_entities(media):
    response = await media.client.head(
        "/api/artifact-library/playable/preview", headers={"Range": "bytes=1-2"}
    )
    assert response.status_code == 200 and not response.content
    assert response.headers["content-length"] == str(len(PAYLOAD))
    assert not media.storage.reads
    response = await media.client.get(
        "/api/artifact-library/playable/preview",
        headers={"Range": "bytes=1-2", "If-Range": '"unverified"'},
    )
    assert response.status_code == 200 and response.content == PAYLOAD
    response = await media.client.get("/api/artifact-library/empty/preview")
    assert response.status_code == 200 and response.content == b""
    assert response.headers["content-length"] == "0"
    response = await media.client.get(
        "/api/artifact-library/empty/preview", headers={"Range": "bytes=0-"}
    )
    assert (
        response.status_code == 416 and response.headers["content-range"] == "bytes */0"
    )


@pytest.mark.asyncio
async def test_audio_mime_alias_is_normalized_and_preview_never_writes(media):
    async with media.factory() as session:
        before = [
            (item.id, item.updated_at, item.size_bytes)
            for item in (
                await session.scalars(select(Artifact).order_by(Artifact.id))
            ).all()
        ]
    response = await media.client.get(
        "/api/artifact-library/playable-audio/preview", headers={"Range": "bytes=0-7"}
    )
    assert (
        response.status_code == 206 and response.headers["content-type"] == "audio/wav"
    )
    async with media.factory() as session:
        after = [
            (item.id, item.updated_at, item.size_bytes)
            for item in (
                await session.scalars(select(Artifact).order_by(Artifact.id))
            ).all()
        ]
    assert before == after


@pytest.mark.asyncio
async def test_stream_disconnect_closes_the_open_storage_reader(media):
    async with media.factory() as session:
        artifact = await session.get(Artifact, "playable")
    response = await preview_response(artifact, media.storage, method="GET")
    assert len(await anext(response.body_iterator)) == 256 * 1024
    await response.body_iterator.aclose()
    assert media.storage.closed == 1
    await response.reader.aclose()  # Releasing twice is harmless.


@pytest.mark.asyncio
async def test_disconnect_during_headers_also_closes_primed_reader(media):
    async with media.factory() as session:
        artifact = await session.get(Artifact, "playable")
    response = await preview_response(artifact, media.storage, method="GET")

    async def disconnected(message):
        raise OSError("Browser closed before the body started")

    with pytest.raises(ClientDisconnect):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}}, None, disconnected
        )
    assert media.storage.closed == 1


@pytest.mark.asyncio
async def test_preview_requires_login_before_any_file_access(media, monkeypatch):
    from landppt.auth.middleware import get_current_user_required, get_db

    media.app.dependency_overrides.pop(get_current_user_required)
    media.app.dependency_overrides[get_db] = lambda: None
    for method in ["GET", "HEAD"]:
        response = await media.client.request(
            method, "/api/artifact-library/playable/preview"
        )
        assert response.status_code == 401
    assert not media.storage.stats and not media.storage.reads


@pytest.mark.asyncio
async def test_storage_failures_do_not_expose_keys_or_partial_success(
    media, monkeypatch
):
    async def unavailable(key):
        raise RuntimeError("PRIVATE_S3_ENDPOINT_OR_KEY")

    monkeypatch.setattr(media.storage, "size", unavailable)
    response = await media.client.get("/api/artifact-library/playable/preview")
    assert response.status_code == 503 and "PRIVATE" not in response.text
    assert not media.storage.reads


@pytest.mark.parametrize(
    "kind,name,mime,expected",
    [
        ("narration_video_export", "a.mp4", "video/mp4", "video"),
        ("narration_audio_export", "a.wav", "audio/wav", "audio"),
        ("narration_audio_export", "a.zip", "audio/wav", None),
        ("narration_video_export", "a.mp4", "text/html", None),
        ("narration_video_export", "a.svg", "video/mp4", None),
        ("image_cache", "a.mp4", "video/mp4", None),
        ("pdf_export", "a.mp4", "video/mp4", None),
        ("narration_video_export", "a.mp4", None, None),
        ("narration_video_export", "a.mp4", "application/octet-stream", None),
    ],
)
def test_inline_format_requires_registered_type_mime_and_extension(
    kind, name, mime, expected
):
    result = preview_format(kind, name, mime)
    assert (result[0] if result else None) == expected


@pytest.mark.asyncio
async def test_local_range_is_bounded_and_cannot_escape_storage(tmp_path):
    storage = LocalArtifactStorage(str(tmp_path / "objects"))
    await storage.put_bytes(PAYLOAD, "nested/media")
    assert await storage.size("nested/media") == len(PAYLOAD)
    assert (
        b"".join(
            [
                chunk
                async for chunk in storage.open_range("nested/media", 400000, 400007)
            ]
        )
        == PAYLOAD[400000:400008]
    )
    with pytest.raises(FileNotFoundError):
        await storage.size("absent")
    with pytest.raises(ValueError):
        await storage.size("../outside")
    with pytest.raises(ValueError):
        await anext(storage.open_range("../outside", 0, 1))


@pytest.mark.asyncio
async def test_s3_uses_remote_range_and_releases_body_on_disconnect_and_error():
    calls, bodies = [], []

    def head_object(**kwargs):
        calls.append(kwargs)
        return {"ContentLength": len(PAYLOAD)}

    def get_object(**kwargs):
        calls.append(kwargs)
        start, end = map(int, kwargs["Range"].removeprefix("bytes=").split("-"))
        body = io.BytesIO(PAYLOAD[start : end + 1])
        bodies.append(body)
        return {"Body": body}

    storage = object.__new__(S3ArtifactStorage)
    storage.bucket = "private"
    storage.client = SimpleNamespace(head_object=head_object, get_object=get_object)
    assert await storage.size("owned") == len(PAYLOAD)
    assert (
        b"".join([chunk async for chunk in storage.open_range("owned", 300000, 300012)])
        == PAYLOAD[300000:300013]
    )
    assert calls[-1] == {
        "Bucket": "private",
        "Key": "owned",
        "Range": "bytes=300000-300012",
    }
    assert bodies[-1].closed
    stream = storage.open_range("owned", 0, len(PAYLOAD) - 1)
    await anext(stream)
    await stream.aclose()
    assert bodies[-1].closed

    def missing(**kwargs):
        raise ClientError(
            {
                "Error": {"Code": "NoSuchKey"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            },
            "HeadObject",
        )

    storage.client.head_object = missing
    with pytest.raises(FileNotFoundError):
        await storage.size("absent")
