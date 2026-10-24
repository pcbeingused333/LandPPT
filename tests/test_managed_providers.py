"""Real database/API regressions for managed services and isolated user keys."""

import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from landppt.database.models import Base, ManagedAIProvider, User, UserAIProviderConfig
from landppt.services import db_config_service as db_config
from landppt.services.managed_provider_service import (
    ManagedProviderError,
    ProviderInput,
    resolve_managed_provider,
    resolve_managed_provider_sync,
)


@pytest_asyncio.fixture
async def environment(tmp_path, monkeypatch):
    import landppt.database.database as database
    from landppt.api import config_api, managed_provider_api
    from landppt.auth.middleware import get_current_user_required

    path = tmp_path / "providers.db"
    # Optional disposable PostgreSQL instance; never accept a production URL.
    port = os.getenv("LANDPPT_PROVIDER_TEST_POSTGRES_PORT")
    if port:
        assert 1 <= int(port) <= 65535
        url = f"postgresql://postgres:landppt-provider-test@127.0.0.1:{int(port)}/landppt_provider_test"
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://")
        )
        sync_engine = create_engine(url)
    else:
        engine = create_async_engine("sqlite+aiosqlite:///" + path.as_posix())
        sync_engine = create_engine("sqlite:///" + path.as_posix())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(sync_engine))
    monkeypatch.setattr(
        db_config, "_db_config_service", db_config.DatabaseConfigService()
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            insert(User),
            [
                dict(id=i, username=f"user{i}", password_hash="unused", is_admin=i == 1)
                for i in (1, 2, 3)
            ],
        )

    async def session_dependency():
        async with sessions() as session:
            yield session

    async def identity(request: Request):
        value = request.headers.get("x-test-user")
        if not value:
            raise HTTPException(401, "Sign in")
        return SimpleNamespace(id=int(value), is_admin=value == "1", username="test")

    app = FastAPI()
    app.include_router(config_api.router)
    app.include_router(managed_provider_api.router)
    app.dependency_overrides[database.get_async_db] = session_dependency
    app.dependency_overrides[get_current_user_required] = identity
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"x-test-user": "1"},
    ) as client:
        yield client, sessions, app
    if port:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    sync_engine.dispose()


async def create(client, **overrides):
    payload = dict(
        name="Example Relay",
        base_url="https://relay.example.com/v1",
        default_model="relay-model",
        description="Service description",
        registration_url="https://relay.example.com/register?ref=landppt",
        recommended_models=["relay-model", "other-model"],
    )
    payload.update(overrides)
    response = await client.post(
        "/admin/api/ai-providers", json=payload, headers={"x-test-user": "1"}
    )
    assert response.status_code == 200, response.text
    return response.json()["provider"]


async def configure(client, provider, user=2, key="secret-user-2", **settings):
    response = await client.put(
        f"/api/managed-providers/{provider['id']}/config",
        headers={"x-test-user": str(user)},
        json=dict(
            api_key=key,
            model="user-model",
            confirmed_base_url=provider["base_url"],
            **settings,
        ),
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_admin_permissions_and_public_catalogue(environment):
    client, _, _ = environment
    provider = await create(client)
    assert (
        await client.get("/admin/api/ai-providers", headers={"x-test-user": "2"})
    ).status_code == 403
    assert (
        await client.post(
            "/admin/api/ai-providers", json={}, headers={"x-test-user": "2"}
        )
    ).status_code == 403
    assert (
        await client.get("/api/managed-providers", headers={"x-test-user": ""})
    ).status_code == 401
    public = (
        await client.get("/api/managed-providers", headers={"x-test-user": "2"})
    ).json()["providers"]
    assert public[0]["registration_url"].endswith("?ref=landppt")
    assert public[0]["provider"] == "custom:" + provider["id"]
    assert public[0]["has_api_key"] is False


@pytest.mark.asyncio
async def test_keys_are_encrypted_and_never_in_catalogue(environment):
    client, sessions, _ = environment
    provider = await create(client)
    result = await configure(client, provider)
    assert "secret-user-2" not in json.dumps(result)
    async with sessions() as session:
        row = await session.scalar(select(UserAIProviderConfig))
        assert row.encrypted_api_key and "secret-user-2" not in row.encrypted_api_key
    own = (
        await client.get("/api/managed-providers", headers={"x-test-user": "2"})
    ).json()
    other = (
        await client.get("/api/managed-providers", headers={"x-test-user": "3"})
    ).json()
    admin = (await client.get("/admin/api/ai-providers")).json()
    assert own["providers"][0]["configured"] is True
    assert other["providers"][0]["has_api_key"] is False
    assert "secret-user-2" not in json.dumps([own, other, admin])
    with pytest.raises(ManagedProviderError, match="API Key"):
        await resolve_managed_provider(3, provider["provider"])
    assert (await resolve_managed_provider(2, provider["provider"]))[
        "api_key"
    ] == "secret-user-2"
    assert (
        resolve_managed_provider_sync(2, provider["provider"])["api_key"]
        == "secret-user-2"
    )


@pytest.mark.asyncio
async def test_reasoning_settings_are_isolated_persisted_and_preserved(environment):
    client, _, _ = environment
    provider = await create(client)
    second = await create(client, name="Second relay")
    await configure(client, provider, enable_reasoning=True, reasoning_effort="xhigh")
    await configure(
        client, provider, user=3, enable_reasoning=True, reasoning_effort="low"
    )
    await configure(client, second)

    catalogue = (
        await client.get("/api/managed-providers", headers={"x-test-user": "2"})
    ).json()["providers"]
    own = next(row for row in catalogue if row["id"] == provider["id"])
    other = next(row for row in catalogue if row["id"] == second["id"])
    assert own["enable_reasoning"] is True and own["reasoning_effort"] == "xhigh"
    assert other["enable_reasoning"] is False and other["reasoning_effort"] == "medium"
    assert (await resolve_managed_provider(3, provider["provider"]))[
        "reasoning_effort"
    ] == "low"

    # Older clients and model-only updates must not reset saved reasoning choices.
    response = await client.put(
        f"/api/managed-providers/{provider['id']}/config",
        headers={"x-test-user": "2"},
        json={"model": "changed-model", "confirmed_base_url": provider["base_url"]},
    )
    assert response.status_code == 200, response.text
    resolved = resolve_managed_provider_sync(2, provider["provider"])
    assert (
        resolved["enable_reasoning"] is True and resolved["reasoning_effort"] == "xhigh"
    )
    assert (
        resolved["api_key"] == "secret-user-2" and resolved["model"] == "changed-model"
    )

    response = await client.put(
        f"/api/managed-providers/{provider['id']}/config",
        headers={"x-test-user": "2"},
        json={"enable_reasoning": False, "confirmed_base_url": provider["base_url"]},
    )
    assert response.status_code == 200
    resolved = await resolve_managed_provider(2, provider["provider"])
    assert (
        resolved["enable_reasoning"] is False
        and resolved["reasoning_effort"] == "xhigh"
    )
    assert resolved["model"] == "changed-model"
    assert (await resolve_managed_provider(3, provider["provider"]))[
        "enable_reasoning"
    ] is True
    await client.delete(
        f"/api/managed-providers/{provider['id']}/config",
        headers={"x-test-user": "2"},
    )
    rows = (
        await client.get("/api/managed-providers", headers={"x-test-user": "2"})
    ).json()["providers"]
    cleared = next(row for row in rows if row["id"] == provider["id"])
    assert (
        cleared["enable_reasoning"] is False and cleared["reasoning_effort"] == "medium"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", ["unsupported", "", None])
async def test_invalid_reasoning_efforts_do_not_change_saved_configuration(
    environment, effort
):
    client, _, _ = environment
    provider = await create(client)
    await configure(client, provider, enable_reasoning=True, reasoning_effort="high")
    response = await client.put(
        f"/api/managed-providers/{provider['id']}/config",
        headers={"x-test-user": "2"},
        json={"reasoning_effort": effort, "confirmed_base_url": provider["base_url"]},
    )
    assert response.status_code == 422
    assert (await resolve_managed_provider(2, provider["provider"]))[
        "reasoning_effort"
    ] == "high"


@pytest.mark.asyncio
async def test_reasoning_migration_upgrades_existing_credentials_idempotently(
    environment,
):
    client, sessions, _ = environment
    provider = await create(client)
    await configure(client, provider)
    from landppt.database.migrations import DatabaseMigration

    async with sessions() as session:
        saved_key = await session.scalar(
            text("SELECT encrypted_api_key FROM user_ai_provider_configs")
        )
        for name in ("enable_reasoning", "reasoning_effort"):
            await session.execute(
                text(f"ALTER TABLE user_ai_provider_configs DROP COLUMN {name}")
            )
        migration = DatabaseMigration()
        await migration._migration_021_up(session)
        await migration._migration_021_up(session)
        await session.commit()
        row = (
            (await session.execute(text("SELECT * FROM user_ai_provider_configs")))
            .mappings()
            .one()
        )
        assert not row["enable_reasoning"] and row["reasoning_effort"] == "medium"
        assert row["encrypted_api_key"] == saved_key and row["model"] == "user-model"
    assert (await resolve_managed_provider(2, provider["provider"]))[
        "api_key"
    ] == "secret-user-2"


@pytest.mark.asyncio
async def test_multiple_services_default_and_role_configuration(
    environment, monkeypatch
):
    client, _, _ = environment
    first = await create(client)
    second = await create(client, name="Second Relay")
    await configure(client, first)
    await configure(client, second, key="second-key")
    assert (
        await client.post(
            "/api/config/default-provider",
            headers={"x-test-user": "2"},
            json={"provider": second["provider"]},
        )
    ).status_code == 200
    config_service = db_config.get_db_config_service()
    await config_service.update_config(
        {
            "outline_model_provider": first["provider"],
            "outline_model_name": "outline-special",
        },
        user_id=2,
    )
    from landppt.ai.providers import AIProviderFactory

    monkeypatch.setattr(
        AIProviderFactory,
        "create_provider",
        lambda name, config: SimpleNamespace(
            model=config["model"], config=config, name=name
        ),
    )
    provider, settings = await db_config.get_user_role_provider(2, "outline")
    assert provider.name == first["provider"] and settings["model"] == "outline-special"
    provider, settings = await db_config.get_user_role_provider(2, "slide")
    assert (
        provider.name == second["provider"]
        and provider.config["api_key"] == "second-key"
    )
    assert settings["model"] == "user-model" and settings["provider"] != "landppt"
    provider, settings = db_config.get_user_role_provider_sync(2, "slide")
    assert provider.name == second["provider"] and settings["model"] == "user-model"


@pytest.mark.asyncio
async def test_address_change_requires_confirmation_and_preserves_key(environment):
    client, _, _ = environment
    provider = await create(client)
    await configure(client, provider, enable_reasoning=True, reasoning_effort="high")
    data = {name: provider[name] for name in ProviderInput.model_fields}
    data["base_url"] = "https://new-relay.example.com/v1"
    response = await client.put("/admin/api/ai-providers/" + provider["id"], json=data)
    assert response.status_code == 200
    with pytest.raises(ManagedProviderError, match="地址已变更"):
        await resolve_managed_provider(2, provider["provider"])
    response = await client.post(
        f"/api/managed-providers/{provider['id']}/models", headers={"x-test-user": "2"}
    )
    assert response.status_code == 400
    public = (
        await client.get("/api/managed-providers", headers={"x-test-user": "2"})
    ).json()["providers"][0]
    assert public["requires_confirmation"] and not public["configured"]
    response = await client.put(
        f"/api/managed-providers/{provider['id']}/config",
        headers={"x-test-user": "2"},
        json={"confirmed_base_url": data["base_url"], "model": "updated-model"},
    )
    assert response.status_code == 200
    config = await resolve_managed_provider(2, provider["provider"])
    assert config["api_key"] == "secret-user-2" and config["model"] == "updated-model"


@pytest.mark.asyncio
async def test_disabled_provider_preserves_personal_config_and_blocks_default(
    environment,
):
    client, _, _ = environment
    provider = await create(client)
    await configure(client, provider)
    data = {name: provider[name] for name in ProviderInput.model_fields}
    data["is_active"] = False
    assert (
        await client.put("/admin/api/ai-providers/" + provider["id"], json=data)
    ).status_code == 200
    with pytest.raises(ManagedProviderError, match="停用"):
        await resolve_managed_provider(2, provider["provider"])
    assert (
        await client.post(
            "/api/config/default-provider",
            headers={"x-test-user": "2"},
            json={"provider": provider["provider"]},
        )
    ).status_code == 400
    own = (
        await client.get("/api/managed-providers", headers={"x-test-user": "2"})
    ).json()["providers"]
    other = (
        await client.get("/api/managed-providers", headers={"x-test-user": "3"})
    ).json()["providers"]
    assert own[0]["has_api_key"] and not own[0]["is_active"] and not other


@pytest.mark.asyncio
async def test_sorting_is_atomic_and_stable(environment):
    client, _, _ = environment
    first = await create(client, sort_order=20)
    second = await create(client, name="First", sort_order=10)
    assert (await client.get("/api/managed-providers")).json()["providers"][0][
        "id"
    ] == second["id"]
    assert (
        await client.post(
            "/admin/api/ai-providers/order", json={"ids": [first["id"], first["id"]]}
        )
    ).status_code == 409
    assert (
        await client.post("/admin/api/ai-providers/order", json={"ids": [first["id"]]})
    ).status_code == 409
    assert (
        await client.post(
            "/admin/api/ai-providers/order", json={"ids": [first["id"], second["id"]]}
        )
    ).status_code == 200
    assert [
        item["id"]
        for item in (await client.get("/api/managed-providers")).json()["providers"]
    ] == [first["id"], second["id"]]


@pytest.mark.asyncio
async def test_clearing_config_is_scoped_to_current_user(environment):
    client, _, _ = environment
    provider = await create(client)
    await configure(client, provider)
    await configure(client, provider, user=3, key="user-3-key")
    assert (
        await client.delete(
            f"/api/managed-providers/{provider['id']}/config",
            headers={"x-test-user": "2"},
        )
    ).status_code == 200
    with pytest.raises(ManagedProviderError):
        await resolve_managed_provider(2, provider["provider"])
    assert (await resolve_managed_provider(3, provider["provider"]))[
        "api_key"
    ] == "user-3-key"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///x",
        "https://user:secret@relay.example.com/v1",
        "https://relay.example.com/v1?key=x",
        "http://localhost/v1",
        "http://127.0.0.1/v1",
        "http://169.254.169.254/v1",
        "http://[::1]/v1",
        "https://relay.example.com/#frag",
        "https://relay.example.com\\evil",
    ],
)
def test_unsafe_api_urls_are_rejected(url):
    with pytest.raises(ValueError):
        ProviderInput(name="Unsafe", base_url=url)


def test_new_tables_compile_for_postgresql():
    for table in (ManagedAIProvider.__table__, UserAIProviderConfig.__table__):
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in ddl


def test_document_processing_preserves_provider_identity_without_environment_keys(
    monkeypatch,
):
    from summeryanyfile.core.llm_manager import LLMManager

    monkeypatch.setenv("OPENAI_API_KEY", "platform-key-must-not-be-used")
    manager = LLMManager()
    assert not manager.validate_configuration(
        "custom:relay", base_url="https://relay.example.com/v1"
    )
    assert manager.validate_configuration(
        "custom:relay", api_key="own-key", base_url="https://relay.example.com/v1"
    )
    model = manager.get_llm(
        provider="custom:relay",
        model="own-model",
        api_key="own-key",
        base_url="https://relay.example.com/v1",
        use_responses_api=True,
        enable_reasoning=True,
        reasoning_effort="high",
    )
    assert model.provider == "custom:relay"
    config = model._build_provider_config()
    assert config["api_key"] == "own-key" and config["use_responses_api"] is True
    assert config["base_url"] == "https://relay.example.com/v1"
    assert config["enable_reasoning"] is True and config["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_factory_reuses_openai_transport_with_separate_identity(monkeypatch):
    from landppt.ai.providers import AIProviderFactory
    import landppt.ai.providers as providers

    seen = []
    monkeypatch.setattr(
        providers,
        "OpenAIProvider",
        lambda config: seen.append(config) or SimpleNamespace(config=config),
    )
    AIProviderFactory.clear_cache()
    first = AIProviderFactory.create_provider(
        "custom:first", {"api_key": "a", "base_url": "https://relay.example.com/v1"}
    )
    second = AIProviderFactory.create_provider(
        "custom:second", {"api_key": "b", "base_url": "https://relay.example.com/v1"}
    )
    assert first is not second and first.config["managed_provider"] is True
    with pytest.raises(ManagedProviderError):
        AIProviderFactory.create_provider("custom:missing", {})
    AIProviderFactory.clear_cache()


@pytest.mark.asyncio
async def test_runtime_config_and_disabled_services_never_fall_back(
    environment, monkeypatch
):
    client, _, _ = environment
    provider = await create(client, use_responses_api=True)
    await configure(client, provider, enable_reasoning=True, reasoning_effort="high")
    await db_config.get_db_config_service().update_config(
        {"default_ai_provider": provider["provider"]}, user_id=2
    )
    from landppt.services.runtime.runtime_config_service import RuntimeConfigService
    from landppt.services.runtime.runtime_provider_service import RuntimeProviderService
    from landppt.services.speech_script_service import SpeechScriptService
    from landppt.services.template.global_master_template_service import (
        GlobalMasterTemplateService,
    )
    from landppt.services.runtime.ai_execution import ExecutionContext

    owner = SimpleNamespace(user_id=2, provider_name=None)
    runtime = RuntimeConfigService(owner)
    config = await runtime._get_current_ai_config_async("outline")
    assert config["llm_provider"] == provider["provider"]
    assert config["api_key"] == "secret-user-2" and config["llm_model"] == "user-model"
    assert config["use_responses_api"] is True
    assert config["enable_reasoning"] is True and config["reasoning_effort"] == "high"
    processing = ExecutionContext.from_mapping(
        "outline", config
    ).to_processing_config_kwargs()
    assert (
        processing["enable_reasoning"] is True
        and processing["reasoning_effort"] == "high"
    )
    assert runtime._get_current_ai_config()["llm_provider"] == provider["provider"]
    assert (
        ExecutionContext.from_mapping("outline", config).to_processing_config_kwargs()[
            "llm_provider"
        ]
        == provider["provider"]
    )
    data = {name: provider[name] for name in ProviderInput.model_fields}
    data["is_active"] = False
    await client.put("/admin/api/ai-providers/" + provider["id"], json=data)
    with pytest.raises(ManagedProviderError):
        await runtime._get_current_ai_config_async("outline")
    with pytest.raises(ManagedProviderError):
        runtime._get_current_ai_config()
    resolver = RuntimeProviderService(owner)
    with pytest.raises(ManagedProviderError):
        await resolver.get_role_provider_async("outline")
    with pytest.raises(ManagedProviderError):
        resolver.get_role_provider("outline")
    with pytest.raises(ManagedProviderError):
        _ = resolver.ai_provider
    with pytest.raises(ManagedProviderError):
        await SpeechScriptService(user_id=2).initialize_async()
    template_service = GlobalMasterTemplateService.__new__(GlobalMasterTemplateService)
    template_service.user_id = 2
    template_service.provider_name = None
    with pytest.raises(ManagedProviderError):
        await template_service._get_template_role_provider_async()


@pytest.mark.asyncio
async def test_model_lookup_uses_only_approved_destination_and_no_redirects(
    environment, monkeypatch
):
    client, _, _ = environment
    provider = await create(client)
    await configure(client, provider)
    import landppt.api.managed_provider_api as api

    original = httpx.AsyncClient
    calls = []

    def respond(request):
        calls.append(request)
        assert str(request.url) == provider["base_url"] + "/models"
        assert request.headers["Authorization"] == "Bearer secret-user-2"
        return httpx.Response(
            200,
            json={
                "data": [{"id": "one"}, {"id": "two"}, {"id": "one"}, {"invalid": 1}]
            },
        )

    def mock_client(**kwargs):
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(api.httpx, "AsyncClient", mock_client)
    response = await client.post(
        f"/api/managed-providers/{provider['id']}/models", headers={"x-test-user": "2"}
    )
    assert response.json()["models"] == ["one", "two"] and len(calls) == 1
    monkeypatch.setattr(
        api.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302, headers={"Location": "https://another.example.com/models"}
                )
            ),
            **kwargs,
        ),
    )
    response = await client.post(
        f"/api/managed-providers/{provider['id']}/models", headers={"x-test-user": "2"}
    )
    assert response.status_code == 502 and "secret-user-2" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enable_reasoning,effort", [(False, "medium"), (True, "high"), (True, "none")]
)
async def test_connection_probe_uses_draft_key_and_redacts_remote_errors(
    environment, monkeypatch, enable_reasoning, effort
):
    client, _, _ = environment
    provider = await create(client)
    from landppt.ai.providers import AIProviderFactory

    calls = []

    class Fake:
        async def chat_completion(self, messages, **kwargs):
            calls.append(kwargs)

    def create_probe(name, config, use_cache):
        assert (
            name == provider["provider"]
            and config["api_key"] == "draft-key"
            and not use_cache
        )
        assert config["enable_reasoning"] is enable_reasoning
        assert config["reasoning_effort"] == effort
        return Fake()

    monkeypatch.setattr(AIProviderFactory, "create_provider", create_probe)
    body = dict(
        api_key="draft-key",
        model="test-model",
        confirmed_base_url=provider["base_url"],
        enable_reasoning=enable_reasoning,
        reasoning_effort=effort,
    )
    response = await client.post(
        f"/api/managed-providers/{provider['id']}/test",
        headers={"x-test-user": "2"},
        json=body,
    )
    assert response.status_code == 200 and calls[0]["max_tokens"] == 16

    class Failed:
        async def chat_completion(self, *args, **kwargs):
            raise RuntimeError("Remote error contains draft-key")

    monkeypatch.setattr(
        AIProviderFactory, "create_provider", lambda *args, **kwargs: Failed()
    )
    response = await client.post(
        f"/api/managed-providers/{provider['id']}/test",
        headers={"x-test-user": "2"},
        json=body,
    )
    assert response.status_code == 502 and "draft-key" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("draft_model", [None, "draft-model"])
async def test_probe_without_reasoning_fields_keeps_saved_choices(
    environment, monkeypatch, draft_model
):
    client, _, _ = environment
    provider = await create(client)
    await configure(client, provider, enable_reasoning=True, reasoning_effort="xhigh")
    from landppt.ai.providers import AIProviderFactory

    def probe(name, config, use_cache):
        assert config["enable_reasoning"] is True
        assert config["reasoning_effort"] == "xhigh"
        assert config["model"] == (draft_model or "user-model")
        return SimpleNamespace(chat_completion=AsyncMock())

    monkeypatch.setattr(AIProviderFactory, "create_provider", probe)
    body = (
        None
        if draft_model is None
        else {"model": draft_model, "confirmed_base_url": provider["base_url"]}
    )
    response = await client.post(
        f"/api/managed-providers/{provider['id']}/test",
        headers={"x-test-user": "2"},
        json=body,
    )
    assert response.status_code == 200, response.text
    assert (await resolve_managed_provider(2, provider["provider"]))[
        "model"
    ] == "user-model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enable_reasoning,effort", [(False, "high"), (True, "none"), (True, "high")]
)
async def test_managed_responses_requests_use_saved_reasoning_including_streams(
    environment, enable_reasoning, effort
):
    client, _, _ = environment
    provider = await create(client, use_responses_api=True)
    await configure(
        client, provider, enable_reasoning=enable_reasoning, reasoning_effort=effort
    )
    from landppt.ai import AIMessage, MessageRole
    from landppt.ai.providers import AIProviderFactory

    instance = await db_config.get_user_ai_provider(2, provider["provider"])
    await instance.client.close()
    calls = []

    async def complete(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            output_text="hello", model="user-model", status="completed", usage=None
        )

    @asynccontextmanager
    async def stream(**kwargs):
        calls.append(kwargs)

        async def events():
            yield SimpleNamespace(type="response.output_text.delta", delta="hello")

        yield events()

    instance.client = SimpleNamespace(
        responses=SimpleNamespace(create=complete, stream=stream)
    )
    try:
        messages = [AIMessage(role=MessageRole.USER, content="Hi")]
        assert (await instance.chat_completion(messages)).content == "hello"
        assert (
            "".join([part async for part in instance.stream_chat_completion(messages)])
            == "hello"
        )
        assert len(calls) == 2
        for body in calls:
            assert body["model"] == "user-model" and "reasoning_effort" not in body
            if enable_reasoning:
                assert body["reasoning"] == {"effort": effort}
            else:
                assert "reasoning" not in body
    finally:
        AIProviderFactory.clear_cache()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enable_reasoning,effort",
    [(False, "high"), (True, "none"), (True, "minimal"), (True, "high"), (True, "max")],
)
async def test_managed_provider_completions_and_streaming(
    environment, caplog, enable_reasoning, effort
):
    client, _, _ = environment
    provider = await create(client)
    await configure(
        client, provider, enable_reasoning=enable_reasoning, reasoning_effort=effort
    )
    from landppt.ai import AIMessage, MessageRole
    import openai

    instance = await db_config.get_user_ai_provider(2, provider["provider"])
    await instance.client.close()
    requests = []
    remote_error = False

    def respond(request):
        if remote_error:
            return httpx.Response(
                401,
                json={
                    "error": {"message": "echoed secret-user-2", "type": "invalid_key"}
                },
            )
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers["Authorization"] == "Bearer secret-user-2"
        assert str(request.url) == provider["base_url"] + "/chat/completions"
        assert body["model"] == "user-model"
        if enable_reasoning:
            assert body["reasoning_effort"] == effort
        else:
            assert "reasoning_effort" not in body
        if body.get("stream"):
            chunks = [
                {
                    "id": "test",
                    "object": "chat.completion.chunk",
                    "model": "user-model",
                    "choices": [
                        {"index": 0, "delta": {"content": word}, "finish_reason": None}
                    ],
                }
                for word in ("hello", " world")
            ]
            return httpx.Response(
                200,
                text="".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                + "data: [DONE]\n\n",
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "model": "user-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    instance.client = openai.AsyncOpenAI(
        api_key="secret-user-2",
        base_url=provider["base_url"],
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond), follow_redirects=False
        ),
    )
    try:
        messages = [AIMessage(role=MessageRole.USER, content="Hi")]
        result = await instance.chat_completion(messages)
        assert result.content == "hello"
        assert (
            "".join([part async for part in instance.stream_chat_completion(messages)])
            == "hello world"
        )
        assert len(requests) == 2
        remote_error = True
        with pytest.raises(ManagedProviderError) as error:
            await instance.chat_completion(messages)
        assert "secret-user-2" not in str(error.value)
        with pytest.raises(ManagedProviderError):
            _ = [part async for part in instance.stream_chat_completion(messages)]
        assert "secret-user-2" not in caplog.text
    finally:
        await instance.client.close()
        from landppt.ai.providers import AIProviderFactory

        AIProviderFactory.clear_cache()
