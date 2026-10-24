"""Edge narration publication, handshake errors and cancellation cleanup."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import edge_tts
import pytest

from landppt.services import narration_service as narration


@pytest.fixture
def edge_narration(monkeypatch, tmp_path):
    from landppt.services import narration_audio_repository

    text = "这是一段讲解音频测试。"
    script = SimpleNamespace(slide_index=0, script_content=text)
    repo = SimpleNamespace(
        get_cached_audio=AsyncMock(return_value=None),
        upsert_audio=AsyncMock(),
        close=Mock(),
    )
    monkeypatch.setattr(
        narration_audio_repository, "NarrationAudioRepository", lambda: repo
    )
    monkeypatch.setattr(narration, "ffprobe_duration_ms", AsyncMock(return_value=1200))
    monkeypatch.setattr(
        narration, "build_cues_json_for_audio", AsyncMock(return_value="[]")
    )
    service = narration.NarrationService()
    monkeypatch.setattr(
        service, "_ensure_speech_scripts", AsyncMock(return_value=[script])
    )
    kwargs = dict(
        project_id="edge-test",
        provider="edge_tts",
        language="zh",
        voice=narration.DEFAULT_VOICE_ZH,
        rate="+10%",
        uploads_dir=str(tmp_path),
    )
    content_hash = narration._hash_for_tts(
        provider="edge_tts",
        language="zh",
        voice=kwargs["voice"],
        rate="+10%",
        text=text,
    )
    output = (
        tmp_path / "narration" / "edge-test" / "zh" / f"slide_0_{content_hash[:12]}.mp3"
    )
    return service, repo, kwargs, output


@pytest.mark.asyncio
async def test_edge_narration_publishes_audio_only_after_success(
    edge_narration, monkeypatch
):
    service, repo, kwargs, output = edge_narration

    async def save(destination):
        Path(destination).write_bytes(b"complete audio")
        assert not output.exists()

    communicate = Mock(return_value=SimpleNamespace(save=save))
    monkeypatch.setattr(edge_tts, "Communicate", communicate)
    results = await service.generate_project_slide_audios(**kwargs)
    assert output.read_bytes() == b"complete audio"
    assert (
        len(results) == 1 and results[0].duration_ms == 1200 and not results[0].cached
    )
    assert results[0].audio_path == str(output)
    assert communicate.call_args.kwargs["voice"] == kwargs["voice"]
    assert communicate.call_args.kwargs["rate"] == "+10%"
    assert repo.upsert_audio.await_args.kwargs["file_path"] == str(output)
    assert not list(output.parent.glob("landppt_tts_*"))
    repo.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429, 500])
async def test_handshake_failure_preserves_audio_and_hides_signed_url(
    edge_narration, monkeypatch, caplog, status
):
    service, repo, kwargs, output = edge_narration
    output.parent.mkdir(parents=True)
    output.write_bytes(b"existing audio")

    async def save(destination):
        Path(destination).write_bytes(b"partial audio")
        raise aiohttp.WSServerHandshakeError(
            SimpleNamespace(
                real_url="wss://speech.example.invalid/?TrustedClientToken=private-token"
            ),
            (),
            status=status,
            message="Invalid response status",
        )

    monkeypatch.setattr(edge_tts, "Communicate", lambda **_: SimpleNamespace(save=save))
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as error:
        await service.generate_project_slide_audios(**kwargs, force_regenerate=True)
    assert "wss://" not in str(error.value) and "private-token" not in caplog.text
    if status == 403:
        assert "7.3.1" in str(error.value)
    assert output.read_bytes() == b"existing audio"
    assert not list(output.parent.glob("landppt_tts_*"))
    repo.upsert_audio.assert_not_awaited()
    repo.close.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_edge_narration_removes_partial_audio(
    edge_narration, monkeypatch
):
    service, repo, kwargs, output = edge_narration

    async def save(destination):
        Path(destination).write_bytes(b"partial audio")
        raise asyncio.CancelledError()

    monkeypatch.setattr(edge_tts, "Communicate", lambda **_: SimpleNamespace(save=save))
    with pytest.raises(asyncio.CancelledError):
        await service.generate_project_slide_audios(**kwargs)
    assert not output.exists() and not list(output.parent.glob("landppt_tts_*"))
    repo.upsert_audio.assert_not_awaited()
    repo.close.assert_called_once()
