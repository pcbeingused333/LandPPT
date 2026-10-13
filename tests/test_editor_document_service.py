"""Isolated SQLite/API coverage for page text edits; no generation or live DB."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from landppt.auth.middleware import get_current_user_required
from landppt.database.models import (
    Base,
    NarrationAudio,
    Project,
    SlideData,
    SpeechScript,
    User,
)
from landppt.database.service import DatabaseService
from landppt.services.editor_document_service import EditorDocumentService
from landppt.web.route_modules import editor_document_routes as routes


@pytest_asyncio.fixture
async def documents(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'documents.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    outline = {
        "title": "保留项目标题",
        "custom": {"references": ["source"]},
        "slides": [
            {
                "title": "封面",
                "slide_type": "title",
                "content_points": ["原始要点"],
                "visual": {"layout": "cover"},
            },
            {
                "title": "第二页",
                "slide_type": "content",
                "content_points": ["保留第二页"],
            },
        ],
    }
    async with factory() as session:
        session.add(User(id=7, username="document-test", password_hash="unused"))
        session.add(
            Project(
                project_id="document-test",
                user_id=7,
                title="项目",
                topic="主题",
                scenario="general",
                status="completed",
                outline=outline,
                slides_html="unchanged combined artwork",
                slides_data=[
                    {
                        "title": "封面",
                        "html_content": "unchanged canvas",
                        "custom": "keep",
                    }
                ],
                confirmed_requirements={"keep": True},
                project_metadata={"renderer": "svg"},
            )
        )
        session.add(
            SlideData(
                project_id="document-test",
                slide_index=0,
                slide_id="stable-cover",
                title="封面",
                content_type="title",
                html_content="unchanged canvas",
                slide_metadata={"locked": True, "renderer": "svg"},
                is_user_edited=False,
            )
        )
        session.add(
            SlideData(
                project_id="document-test",
                slide_index=1,
                slide_id="stable-second",
                title="第二页",
                content_type="content",
                html_content="second canvas",
            )
        )
        session.add(
            SpeechScript(
                project_id="document-test",
                slide_index=0,
                language="zh",
                slide_title="封面",
                script_content="原始讲稿",
                generation_type="full",
                tone="formal",
                target_audience="general_public",
                language_complexity="moderate",
                speaking_pace="normal",
                custom_style_prompt="保留生成配置",
                estimated_duration="1分钟",
                speaker_notes="原始备注",
            )
        )
        await session.commit()
    yield factory, outline
    await engine.dispose()


async def snapshot(factory, index=0, language="zh"):
    async with factory() as session:
        return await EditorDocumentService(session).read(
            "document-test", 7, index, language
        )


async def save(factory, document, kind, fields, **extra):
    body = routes.DocumentPatch(
        kind=kind,
        revision=document[f"{kind}_revision"],
        slide_id=document["slide_id"],
        **{kind: fields},
        **extra,
    )
    async with factory() as session:
        return await EditorDocumentService(session).save(
            "document-test", 7, document["slide_index"], document["language"], body
        )


@pytest.mark.asyncio
async def test_outline_merge_preserves_artwork_other_pages_and_unknown_fields(
    documents,
):
    factory, original = documents
    before = await snapshot(factory)
    after = await save(
        factory,
        before,
        "outline",
        {
            "title": "新标题",
            "slide_type": "custom-section",
            "content_points": ["新要点"],
            "description": "新增说明",
        },
    )
    assert after["outline_revision"] != before["outline_revision"]
    assert after["outline"]["visual"] == original["slides"][0]["visual"]
    async with factory() as session:
        project = await session.scalar(select(Project))
        slide = await session.scalar(
            select(SlideData).where(SlideData.slide_index == 0)
        )
        assert project.outline["slides"][1] == original["slides"][1]
        assert project.outline["custom"] == original["custom"]
        assert json.loads(project.outline["content"])["slides"][0]["title"] == "新标题"
        assert slide.title == project.slides_data[0]["title"] == "新标题"
        assert slide.content_type == "custom-section"
        assert slide.slide_metadata["locked"] is True
        assert (
            slide.html_content
            == project.slides_data[0]["html_content"]
            == "unchanged canvas"
        )
        assert project.slides_data[0]["custom"] == "keep"
        assert project.slides_html == "unchanged combined artwork"
        assert project.status == "completed" and project.confirmed_requirements == {
            "keep": True
        }
        assert slide.is_user_edited is False


@pytest.mark.asyncio
async def test_speech_create_edit_clear_optional_fields_and_language_isolation(
    documents,
):
    factory, _ = documents
    english = await snapshot(factory, language="en")
    assert english["script"] is None
    created = await save(
        factory,
        english,
        "speech",
        {
            "slide_title": "English title",
            "script_content": "English script",
            "estimated_duration": "2 minutes",
            "speaker_notes": "Pause here",
        },
    )
    assert created["script"]["id"] and created["script"]["language"] == "en"
    cleared = await save(
        factory,
        created,
        "speech",
        {
            "slide_title": "English title",
            "script_content": "Revised script",
            "estimated_duration": "",
            "speaker_notes": "",
        },
    )
    assert (
        cleared["script"]["estimated_duration"]
        == cleared["script"]["speaker_notes"]
        == ""
    )
    chinese = await snapshot(factory)
    await save(
        factory,
        chinese,
        "speech",
        {"slide_title": "封面", "script_content": "中文修改"},
    )
    async with factory() as session:
        script = await session.scalar(
            select(SpeechScript).where(SpeechScript.language == "zh")
        )
        assert script.generation_type == "full" and script.tone == "formal"
        assert script.custom_style_prompt == "保留生成配置"
        assert (await snapshot(factory, language="en"))["script"][
            "script_content"
        ] == "Revised script"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["outline", "speech"])
async def test_stale_revision_refuses_overwrite(documents, kind):
    factory, _ = documents
    before = await snapshot(factory)
    fields = (
        {"title": "另一窗口", "slide_type": "title"}
        if kind == "outline"
        else {"slide_title": "封面", "script_content": "另一窗口讲稿"}
    )
    updated = await save(factory, before, kind, fields)
    with pytest.raises(HTTPException) as error:
        await save(factory, before, kind, fields)
    assert error.value.status_code == 409
    assert (await snapshot(factory))[f"{kind}_revision"] == updated[f"{kind}_revision"]


@pytest.mark.asyncio
async def test_different_page_edits_merge_without_losing_each_other(documents):
    factory, _ = documents
    first, second = await snapshot(factory), await snapshot(factory, index=1)
    await save(
        factory, first, "outline", {"title": "第一页修改", "slide_type": "title"}
    )
    await save(
        factory, second, "outline", {"title": "第二页修改", "slide_type": "content"}
    )
    assert (await snapshot(factory))["outline"]["title"] == "第一页修改"
    assert (await snapshot(factory, index=1))["outline"]["title"] == "第二页修改"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "index,user_id,identity,status",
    [
        (0, 8, None, 404),
        (-1, 7, None, 404),
        (10, 7, None, 404),
        (0, 7, "stable-second", 409),
    ],
)
async def test_ownership_bounds_and_identity(
    documents, index, user_id, identity, status
):
    factory, _ = documents
    async with factory() as session:
        with pytest.raises(HTTPException) as error:
            await EditorDocumentService(session).read(
                "document-test", user_id, index, "zh", identity
            )
        assert error.value.status_code == status


@pytest.mark.asyncio
async def test_deleted_or_reordered_slide_cannot_receive_stale_draft(documents):
    factory, _ = documents
    before = await snapshot(factory)
    async with factory() as session:
        slides = list(
            (
                await session.scalars(select(SlideData).order_by(SlideData.slide_index))
            ).all()
        )
        slides[0].slide_index, slides[1].slide_index = 1, 0
        await session.commit()
    with pytest.raises(HTTPException) as error:
        await save(
            factory,
            before,
            "speech",
            {"slide_title": "旧封面", "script_content": "不能写入第二页"},
        )
    assert error.value.status_code == 409
    assert (await snapshot(factory))["script"]["script_content"] == "原始讲稿"


@pytest.mark.asyncio
async def test_routes_require_auth_validate_payload_and_disable_caching(
    documents, monkeypatch
):
    factory, _ = documents
    monkeypatch.setattr(routes, "AsyncSessionLocal", factory)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=7)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        path = "/api/projects/document-test/editor-documents/0"
        response = await client.get(path)
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
        )
        before = response.json()["document"]
        good = {
            "kind": "speech",
            "revision": before["speech_revision"],
            "slide_id": before["slide_id"],
            "speech": {"slide_title": "封面", "script_content": "保存正文"},
        }
        for patch in [
            {**good, "speech": {"slide_title": "封面", "script_content": " "}},
            {**good, "outline": {"title": "bad", "slide_type": "title"}},
            {**good, "revision": "bad"},
        ]:
            assert (await client.patch(path, json=patch)).status_code == 422
        assert (await client.get(path + "?language=invalid")).status_code == 422
        response = await client.patch(path, json=good)
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
        )
        assert response.json()["document"]["script"]["script_content"] == "保存正文"
        app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
            id=8
        )
        assert (await client.patch(path, json=good)).status_code == 404
        app.dependency_overrides.clear()
        assert (await client.get(path)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_concurrent_manual_creation_does_not_duplicate_or_overwrite(documents):
    factory, _ = documents
    before = await snapshot(factory, language="en")

    async def write(content):
        try:
            await save(
                factory,
                before,
                "speech",
                {"slide_title": "English", "script_content": content},
            )
            return 200
        except HTTPException as error:
            return error.status_code

    outcomes = await asyncio.gather(write("First writer"), write("Second writer"))
    assert sorted(outcomes) == [200, 409]
    async with factory() as session:
        scripts = list(
            (
                await session.scalars(
                    select(SpeechScript).where(SpeechScript.language == "en")
                )
            ).all()
        )
        assert len(scripts) == 1


@pytest.mark.asyncio
async def test_missing_outline_uses_slide_metadata_without_writing_on_read(documents):
    factory, _ = documents
    async with factory() as session:
        project = await session.scalar(select(Project))
        project.outline = None
        await session.commit()
    before = await snapshot(factory)
    assert before["outline"]["title"] == "封面"
    assert before["outline"]["slide_type"] == "title"
    async with factory() as session:
        assert (await session.scalar(select(Project))).outline is None
    await save(factory, before, "outline", {"title": "补充大纲", "slide_type": "title"})
    assert (await snapshot(factory))["outline"]["title"] == "补充大纲"


@pytest.mark.asyncio
async def test_drafts_can_save_to_same_page_after_completed_reorder(documents):
    factory, _ = documents
    before = await snapshot(factory)
    async with factory() as session:
        assert await DatabaseService(session).apply_slide_structure_operation(
            "document-test",
            {"type": "move", "slide_index": 0, "to_index": 1},
            user_id=7,
        )
        project = await session.scalar(select(Project))
        outline = dict(project.outline)
        outline["slides"] = [
            dict(outline["slides"][1], page_number=1),
            dict(outline["slides"][0], page_number=2),
        ]
        project.outline = outline
        await session.commit()
    before["slide_index"] = 1
    saved = await save(
        factory, before, "outline", {"title": "移动后保存的大纲", "slide_type": "title"}
    )
    assert saved["slide_id"] == "stable-cover" and saved["slide_index"] == 1
    saved = await save(
        factory,
        before,
        "speech",
        {"slide_title": "移动后保存的讲稿", "script_content": "保留草稿并保存到同一页"},
    )
    assert saved["script"]["slide_index"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,expected",
    [
        ({"type": "move", "slide_index": 0, "to_index": 1}, {0: 1, 1: 0}),
        ({"type": "move", "slide_index": 1, "to_index": 0}, {0: 1, 1: 0}),
        ({"type": "insert", "slide_index": 0}, {0: 1, 1: 2}),
        ({"type": "delete", "slide_index": 0}, {1: 0}),
    ],
)
async def test_native_structure_operations_keep_speech_languages_and_audio_with_pages(
    documents, operation, expected
):
    factory, _ = documents
    for index in (0, 1):
        for language in ("zh", "en"):
            document = await snapshot(factory, index, language)
            await save(
                factory,
                document,
                "speech",
                {
                    "slide_title": f"Page {index}",
                    "script_content": f"page-{index}-{language}",
                },
            )
    async with factory() as session:
        for index in (0, 1):
            for language in ("zh", "en"):
                session.add(
                    NarrationAudio(
                        project_id="document-test",
                        slide_index=index,
                        language=language,
                        voice="test-voice",
                        content_hash="a" * 64,
                        file_path=f"page-{index}-{language}.mp3",
                    )
                )
        await session.commit()
        assert not await DatabaseService(session).apply_slide_structure_operation(
            "document-test", operation, user_id=8
        )
        assert await DatabaseService(session).apply_slide_structure_operation(
            "document-test", operation, user_id=7
        )
    async with factory() as session:
        scripts = list((await session.scalars(select(SpeechScript))).all())
        audio = list((await session.scalars(select(NarrationAudio))).all())
        assert len(scripts) == len(audio) == len(expected) * 2
        for source, destination in expected.items():
            for language in ("zh", "en"):
                assert any(
                    item.slide_index == destination
                    and item.script_content == f"page-{source}-{language}"
                    for item in scripts
                )
                assert any(
                    item.slide_index == destination
                    and item.file_path == f"page-{source}-{language}.mp3"
                    for item in audio
                )
