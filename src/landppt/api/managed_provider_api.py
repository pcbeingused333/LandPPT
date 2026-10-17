"""Admin catalogue and authenticated per-user AI provider endpoints."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.middleware import get_current_user_required
from ..core.config import app_config
from ..database.database import get_async_db
from ..database.models import ManagedAIProvider, User, UserAIProviderConfig
from ..services.managed_provider_service import (
    ManagedProviderError,
    ManagedProviderService,
    ProviderInput,
    UserProviderInput,
)
from ..web.admin_routes import get_admin_user_required, templates

router = APIRouter(tags=["AI Provider Management"])


@router.get("/admin/ai-providers")
async def provider_admin_page(
    request: Request, user: User = Depends(get_admin_user_required)
):
    return templates.TemplateResponse(
        "pages/admin/ai_providers.html",
        {
            "request": request,
            "user": user,
            "credits_enabled": app_config.enable_credits_system,
        },
    )


@router.get("/admin/api/ai-providers")
async def admin_catalogue(
    user: User = Depends(get_admin_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    return {
        "success": True,
        "providers": await ManagedProviderService(session).catalogue(admin=True),
    }


@router.post("/admin/api/ai-providers")
async def create_provider(
    data: ProviderInput,
    user: User = Depends(get_admin_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    return {
        "success": True,
        "provider": await ManagedProviderService(session).save(data),
    }


class ProviderOrder(BaseModel):
    ids: list[str] = Field(max_length=1000)


@router.post("/admin/api/ai-providers/order")
async def order_providers(
    data: ProviderOrder,
    user: User = Depends(get_admin_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    providers = (
        await session.scalars(select(ManagedAIProvider).with_for_update())
    ).all()
    if len(set(data.ids)) != len(data.ids) or set(data.ids) != {
        provider.id for provider in providers
    }:
        raise HTTPException(409, "提供商列表已变化，请刷新后重新排序")
    positions = {provider_id: index * 10 for index, provider_id in enumerate(data.ids)}
    for provider in providers:
        provider.sort_order = positions[provider.id]
    await session.commit()
    return {"success": True}


@router.put("/admin/api/ai-providers/{provider_id}")
async def edit_provider(
    provider_id: str,
    data: ProviderInput,
    user: User = Depends(get_admin_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    try:
        return {
            "success": True,
            "provider": await ManagedProviderService(session).save(data, provider_id),
        }
    except ManagedProviderError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/api/managed-providers")
async def user_catalogue(
    user: User = Depends(get_current_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    return {
        "success": True,
        "providers": await ManagedProviderService(session).catalogue(user.id),
    }


@router.put("/api/managed-providers/{provider_id}/config")
async def save_user_provider(
    provider_id: str,
    data: UserProviderInput,
    user: User = Depends(get_current_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    try:
        return {
            "success": True,
            "provider": await ManagedProviderService(session).save_user(
                user.id, provider_id, data
            ),
        }
    except ManagedProviderError as exc:
        raise HTTPException(400, str(exc)) from None


@router.delete("/api/managed-providers/{provider_id}/config")
async def clear_user_provider(
    provider_id: str,
    user: User = Depends(get_current_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    await session.execute(
        delete(UserAIProviderConfig).where(
            UserAIProviderConfig.user_id == user.id,
            UserAIProviderConfig.provider_id == provider_id,
        )
    )
    await session.commit()
    return {"success": True}


async def _probe_config(session, user_id, provider_id, data):
    try:
        return await ManagedProviderService(session).resolve(
            user_id, provider_id, **(data.model_dump() if data else {})
        )
    except ManagedProviderError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/managed-providers/{provider_id}/models")
async def provider_models(
    provider_id: str,
    data: UserProviderInput | None = None,
    user: User = Depends(get_current_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    config = await _probe_config(session, user.id, provider_id, data)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(
                config["base_url"] + "/models",
                headers={"Authorization": "Bearer " + config["api_key"]},
            )
            response.raise_for_status()
            records = response.json().get("data", [])
            models = list(
                dict.fromkeys(
                    item["id"]
                    for item in records
                    if isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and item["id"]
                )
            )
        return {"success": True, "models": models[:2000]}
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        raise HTTPException(
            502, "模型列表获取失败，可手动填写模型名称或使用推荐模型"
        ) from None


@router.post("/api/managed-providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    data: UserProviderInput | None = None,
    user: User = Depends(get_current_user_required),
    session: AsyncSession = Depends(get_async_db),
):
    config = await _probe_config(session, user.id, provider_id, data)
    if not config.get("model"):
        raise HTTPException(400, "请先填写用于测试的模型名称")
    from ..ai import AIMessage, AIProviderFactory, MessageRole

    provider = None
    try:
        config["llm_timeout_seconds"] = 30
        provider = AIProviderFactory.create_provider(
            config.pop("provider_name"), config, use_cache=False
        )
        await provider.chat_completion(
            [AIMessage(role=MessageRole.USER, content="Reply with OK.")], max_tokens=16
        )
    except Exception:
        # Provider error bodies can contain request credentials. Return a fixed message.
        raise HTTPException(
            502, "连接测试失败，请检查 API Key、模型名称和接口地址"
        ) from None
    finally:
        client = getattr(provider, "client", None)
        if client is not None:
            await client.close()
    return {"success": True, "message": "连接成功"}
