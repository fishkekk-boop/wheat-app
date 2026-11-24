# src/wheat_app/features/auth/service.py
"""Auth: 业务异常 + 业务逻辑"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from jwt.exceptions import InvalidTokenError

from wheat_app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    Forbidden,
    InvalidCredentials,
)
from wheat_app.core.security import (
    DUMMY_HASH,
    hash_password_async,
    verify_password_async,
)
from wheat_app.features.auth.exceptions import (
    DeleteOnlyOne,
    IdentifierExists,
    IdentityAlreadyTaken,
    IdentityNotFound,
    ProviderExists,
    UserDisabled,
    UserNotFound,
)
from wheat_app.features.auth.models import (
    AuthIdentity,
    AuthProvider,
    User,
    UserRole,
    UserStatus,
)
from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AuthSession:
    user: User
    access_token: str
    refresh_token: str


class AuthService:
    _DEFAULT_NICKNAME_PREFIX = "麦田用户"

    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo

    def _generate_default_nickname(self) -> str:
        """拼接默认用户昵称"""
        return f"{self._DEFAULT_NICKNAME_PREFIX}_{secrets.token_hex(3)}"

    def issue_session(self, user: User) -> AuthSession:
        """构造 Tokens + User 返回模型，login register 共用"""
        return AuthSession(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=user,
        )

    #  ---- 注册 ----

    async def _create_account(
        self,
        *,
        provider: AuthProvider,
        identifier: str,
        nickname: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> User:
        """新用户数据落库"""
        try:
            return await self.repo.create_user_with_identity(
                provider=provider,
                identifier=identifier,
                nickname=nickname,
                secret_hash=secret_hash,
                is_verified=is_verified,
            )
        except ConflictError as e:
            raise IdentityAlreadyTaken() from e

    async def register_with_password(
        self, *, account: str, password: str, nickname: str | None = None
    ) -> User:
        logger.info("register_attempt", account=account)
        try:
            user = await self._create_account(
                provider=AuthProvider.PASSWORD,
                identifier=account,
                nickname=nickname or self._generate_default_nickname(),
                secret_hash=await hash_password_async(password),
                is_verified=True,  # 密码注册视为已验证
            )
        except IdentityAlreadyTaken:
            logger.warning("register_conflict", account=account)
            raise
        logger.info("register_success", user_id=str(user.id), account=account)
        return user

    #  ---- 登录 ----

    async def _complete_login(self, identity: AuthIdentity) -> User:
        """校验账号存在且状正常"""
        user = await self.repo.get_user_by_id(identity.user_id)
        if not user:
            logger.warning(
                "login_failed", identity_id=str(identity.id), reason="user_missing"
            )
            raise InvalidCredentials("用户名或密码错误")
        if user.status != UserStatus.ACTIVE:
            logger.warning(
                "login_failed", identity_id=str(identity.id), reason="inactive_user"
            )
            raise InvalidCredentials("用户状态异常，禁止登录")
        now = datetime.now(UTC)
        identity.last_used_at = now
        await self.repo.update_identity(identity)
        user.last_login_at = now
        await self.repo.update_user(user)
        logger.info(
            "login_success", user_id=str(user.id), provider=identity.provider.value
        )
        return user

    async def login_with_password(self, *, account: str, password: str) -> User:
        """校验凭据；通过后交给 _complete_login 处理登录副作用"""
        logger.info("login_attempt", provider="password", identifier=account)
        identity = await self.repo.get_identity(AuthProvider.PASSWORD, account)
        if not identity or not identity.secret_hash:
            await verify_password_async(password, DUMMY_HASH)
            logger.warning(
                "login_failed", identifier=account, reason="invalid_credentials"
            )
            raise InvalidCredentials("用户名或密码错误")

        if not await verify_password_async(password, identity.secret_hash):
            logger.warning(
                "login_failed", identifier=account, reason="invalid_credentials"
            )
            raise InvalidCredentials("用户名或密码错误")

        return await self._complete_login(identity)

    #  ---- 查用户 ----

    async def _load_user(self, user_id: UUID) -> User:
        user = await self.repo.get_user_by_id(user_id)
        if user is None:
            raise UserNotFound()
        return user

    async def get_user(self, user_id: UUID) -> User:
        return await self._load_user(user_id)

    async def require_active_user(self, user_id: UUID) -> User:  # 给认证，401
        user = await self._load_user(user_id)
        if user.status is not UserStatus.ACTIVE:
            raise UserDisabled()
        return user

    async def user_from_token_payload(self, payload: dict) -> User:
        """把已解码的 token payload 还原成可用用户；失败一律 401。"""
        sub = payload.get("sub")
        if sub is None:
            logger.warning("auth_failed", reason="missing_sub")
            raise AuthenticationError("无效 Token")
        try:
            user_id = UUID(sub)
        except ValueError as e:
            logger.warning("auth_failed", reason="invalid_sub_format")
            raise AuthenticationError("无效 Token") from e
        try:
            return await self.require_active_user(user_id)
        except UserNotFound as e:
            raise AuthenticationError("身份凭证无效或已过期") from e

    async def get_user_identities(self, user_id: UUID) -> list[AuthIdentity]:
        return await self.repo.get_identities_by_user_id(user_id)

    # ---- 更新 ----
    async def update_user_profile(
        self,
        *,
        user: User,
        nickname: str | None,
        bio: str | None,
        avatar_url: str | None,
    ) -> User:
        """根据 Token 更新用户信息"""
        if nickname is not None:
            user.nickname = nickname
        if bio is not None:
            user.bio = bio
        if avatar_url is not None:
            user.avatar_url = avatar_url
        logger.info(
            "update_user_profile_success",
            user_id=str(user.id),
            nickname=nickname,
            bio=bio,
            avatar_url=avatar_url,
        )
        return await self.repo.update_user(user)

    async def bind_identifier(
        self,
        *,
        user: User,
        provider: AuthProvider,
        identifier: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> AuthIdentity:
        exists = await self.repo.get_identities_by_provider(provider, identifier)
        if exists:
            logger.warning("bind_provider_failed", reason="provider:identifier_exists")
            raise IdentifierExists(f"{provider=}:{identifier=}已被使用")
        identities = await self.repo.get_identities_by_user_id(user.id)
        for i in identities:
            if i.provider == provider:
                logger.warning("bind_provider_failed", reason="provider_exists")
                raise ProviderExists(
                    f"user_id={i.user_id}已绑定 {provider=}:{identifier=}"
                )
        return await self.repo.add_identity(
            user_id=user.id,
            provider=provider,
            identifier=identifier,
            secret_hash=secret_hash,
            is_verified=is_verified,
        )

    async def unbind_identifier(
        self, *, user: User, provider: AuthProvider, current_password: str
    ) -> None:
        identities = await self.repo.get_identities_by_user_id(user.id)

        target = next((i for i in identities if i.provider == provider), None)
        if target is None:
            raise IdentityNotFound(provider)
        password_identity = next(
            (i for i in identities if i.provider == AuthProvider.PASSWORD), None
        )
        if password_identity is None or not await verify_password_async(
            current_password, password_identity.secret_hash or ""
        ):
            raise InvalidCredentials()

        if len(identities) <= 1:
            raise DeleteOnlyOne()
        await self.repo.delete_identity(target)

    # ---- Token ----

    async def refresh_session(self, token: str) -> AuthSession:
        """校验 refresh token，并签发一对新的 token（旧 token 在有效期内仍可用）。"""
        try:
            payload = decode_token(token, "refresh")
        except InvalidTokenError as e:
            logger.warning("refresh_failed", reason="invalid_token")
            raise AuthenticationError("Refresh Token 无效或已过期") from e
        user = await self.user_from_token_payload(payload)
        return self.issue_session(user)

    # ---- 删除 ----
    async def delete_user(self, user_id: UUID, operator_user: User) -> None:
        if operator_user.role != UserRole.ADMIN:
            logger.warning("delete_user_fialed", reason="forbidden")
            raise Forbidden()
        user = await self.get_user(user_id)
        user.status = UserStatus.DELETED
        await self.repo.update_user(user)
        logger.info("delete_user_success", operator=operator_user.id, deleted=user_id)
