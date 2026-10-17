"""Managed OpenAI services, user credentials and runtime configuration."""

import base64
import hashlib
import ipaddress
import uuid
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import app_config
from ..database.models import ManagedAIProvider, UserAIProviderConfig

PREFIX = "custom:"


class ManagedProviderError(ValueError):
    """A selected managed service must never fall back to another provider."""


def is_managed_provider(name) -> bool:
    return isinstance(name, str) and name.startswith(PREFIX)


def validate_url(value: str, *, api: bool = False) -> str:
    value = value.strip()
    if not value and not api:
        return ""
    try:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            raise ValueError()
        _ = url.port
        if any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
            raise ValueError()
        if api:
            if url.query or url.fragment:
                raise ValueError()
            host = url.hostname.lower().rstrip(".")
            if host == "localhost" or host.endswith((".localhost", ".local")):
                raise ValueError()
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                raise ValueError()
    except ValueError:
        raise ValueError(
            "请填写有效的 HTTP/HTTPS 地址；API 地址须为公共服务地址且不含凭据、查询参数或片段"
        ) from None
    if api:
        return urlunsplit(
            (url.scheme, url.netloc.lower(), url.path.rstrip("/"), "", "")
        )
    return value


class ProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    logo_url: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=2000)
    website_url: str = Field(default="", max_length=2000)
    registration_url: str = Field(default="", max_length=2000)
    base_url: str = Field(max_length=1000)
    default_model: str = Field(default="", max_length=200)
    recommended_models: list[str] = Field(default_factory=list, max_length=200)
    use_responses_api: bool = False
    sort_order: int = Field(default=0, ge=-1000000, le=1000000)
    is_active: bool = True

    @field_validator("logo_url", "website_url", "registration_url")
    @classmethod
    def check_link(cls, value):
        return validate_url(value)

    @field_validator("base_url")
    @classmethod
    def check_base(cls, value):
        return validate_url(value, api=True)

    @field_validator("recommended_models")
    @classmethod
    def check_models(cls, values):
        if any(not value.strip() or len(value.strip()) > 200 for value in values):
            raise ValueError("模型名称须为 1 至 200 个字符")
        return list(dict.fromkeys(value.strip() for value in values))


class UserProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    api_key: str | None = Field(default=None, max_length=4096)
    model: str = Field(default="", max_length=200)
    confirmed_base_url: str = Field(max_length=1000)


def _cipher():
    key = hashlib.sha256(
        ("landppt:managed-provider:" + app_config.secret_key).encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _decrypt(value):
    try:
        return _cipher().decrypt(value.encode()).decode() if value else ""
    except InvalidToken:
        raise ManagedProviderError("提供商密钥无法解密，请重新填写 API Key") from None


def provider_dict(provider, config=None):
    result = {key: getattr(provider, key) for key in ProviderInput.model_fields}
    result.update(id=provider.id, provider=PREFIX + provider.id)
    if config is not None:
        result.update(
            has_api_key=bool(config.encrypted_api_key),
            model=config.model,
            requires_confirmation=config.accepted_base_url != provider.base_url,
            configured=bool(config.encrypted_api_key)
            and config.accepted_base_url == provider.base_url
            and provider.is_active,
        )
    else:
        result.update(
            has_api_key=False,
            model=provider.default_model,
            requires_confirmation=False,
            configured=False,
        )
    return result


def runtime_config(
    provider, config, *, api_key=None, model=None, confirmed_base_url=None
):
    if provider is None or not provider.is_active:
        raise ManagedProviderError(
            "所选 AI 提供商已停用或不存在，请在 AI 配置中重新选择"
        )
    supplied_key = str(api_key or "").strip()
    if config is None and not supplied_key:
        raise ManagedProviderError("请先为所选 AI 提供商配置 API Key")
    accepted = (
        confirmed_base_url
        if confirmed_base_url is not None
        else (config.accepted_base_url if config else "")
    )
    if accepted != provider.base_url:
        raise ManagedProviderError(
            "提供商 API 地址已变更，请在 AI 配置中确认新地址并保存"
        )
    key = supplied_key or (_decrypt(config.encrypted_api_key) if config else "")
    if not key:
        raise ManagedProviderError("请先为所选 AI 提供商配置 API Key")
    return {
        "provider_name": PREFIX + provider.id,
        "api_key": key,
        "base_url": provider.base_url,
        "model": model or (config.model if config else "") or provider.default_model,
        "use_responses_api": provider.use_responses_api,
        "enable_reasoning": False,
    }


class ManagedProviderService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, provider_id):
        provider = await self.session.get(ManagedAIProvider, provider_id)
        if provider is None:
            raise ManagedProviderError("AI 提供商不存在")
        return provider

    async def user_config(self, user_id, provider_id):
        return await self.session.scalar(
            select(UserAIProviderConfig).where(
                UserAIProviderConfig.user_id == user_id,
                UserAIProviderConfig.provider_id == provider_id,
            )
        )

    async def catalogue(self, user_id=None, *, admin=False):
        if admin:
            providers = (
                await self.session.scalars(
                    select(ManagedAIProvider).order_by(
                        ManagedAIProvider.sort_order,
                        ManagedAIProvider.created_at,
                        ManagedAIProvider.id,
                    )
                )
            ).all()
            return [provider_dict(provider) for provider in providers]
        rows = (
            await self.session.execute(
                select(ManagedAIProvider, UserAIProviderConfig)
                .outerjoin(
                    UserAIProviderConfig,
                    (UserAIProviderConfig.provider_id == ManagedAIProvider.id)
                    & (UserAIProviderConfig.user_id == user_id),
                )
                .where(
                    or_(
                        ManagedAIProvider.is_active.is_(True),
                        UserAIProviderConfig.id.is_not(None),
                    )
                )
                .order_by(
                    ManagedAIProvider.sort_order,
                    ManagedAIProvider.created_at,
                    ManagedAIProvider.id,
                )
            )
        ).all()
        return [provider_dict(provider, config) for provider, config in rows]

    async def save(self, data: ProviderInput, provider_id=None):
        provider = (
            await self.get(provider_id)
            if provider_id
            else ManagedAIProvider(id=str(uuid.uuid4()))
        )
        for name, value in data.model_dump().items():
            setattr(provider, name, value)
        self.session.add(provider)
        await self.session.commit()
        return provider_dict(provider)

    async def save_user(self, user_id, provider_id, data: UserProviderInput):
        provider = await self.get(provider_id)
        config = await self.user_config(user_id, provider_id)
        # Validate the new destination before decrypting or sending any saved key.
        runtime_config(provider, config, **data.model_dump())
        if config is None:
            config = UserAIProviderConfig(user_id=user_id, provider_id=provider_id)
            self.session.add(config)
        if data.api_key:
            config.encrypted_api_key = _cipher().encrypt(data.api_key.encode()).decode()
        config.model = data.model or provider.default_model
        config.accepted_base_url = provider.base_url
        await self.session.commit()
        return provider_dict(provider, config)

    async def resolve(self, user_id, provider_id, **overrides):
        return runtime_config(
            await self.get(provider_id),
            await self.user_config(user_id, provider_id),
            **overrides,
        )


async def resolve_managed_provider(user_id, name):
    from ..database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await ManagedProviderService(session).resolve(
            user_id, name.removeprefix(PREFIX)
        )


def resolve_managed_provider_sync(user_id, name):
    from ..database.database import SessionLocal

    with SessionLocal() as session:
        provider_id = name.removeprefix(PREFIX)
        provider = session.get(ManagedAIProvider, provider_id)
        config = session.scalar(
            select(UserAIProviderConfig).where(
                UserAIProviderConfig.user_id == user_id,
                UserAIProviderConfig.provider_id == provider_id,
            )
        )
        return runtime_config(provider, config)
