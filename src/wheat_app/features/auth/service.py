# src/wheat_app/features/auth/service.py
"""Auth: 业务异常 + 业务逻辑"""

import secrets
from datetime import UTC, datetime
from uuid import UUID

import structlog
from jwt.exceptions import InvalidTokenError

from wheat_app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidCredentials,
)
from wheat_app.core.security import DUMMY_HASH, hash_secret_async, verify_password_async
from wheat_app.features.auth.exceptions import IdentityAlreadyTaken, UserNotFound
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User, UserStatus
from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.schemas import (
    AuthResponse,
    PrivateUserOut,
    PublicUserOut,
)
from wheat_app.features.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

logger = structlog.get_logger(__name__)


class AuthService:
    _DEFAULT_NICKNAME_PREFIX = "麦田用户"

    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo

    def _generate_default_nickname(self) -> str:
        """拼接默认用户昵称"""
        return f"{self._DEFAULT_NICKNAME_PREFIX}_{secrets.token_hex(3)}"

    def build_auth_response(self, user: User) -> AuthResponse:
        """构造 Tokens + User 返回模型，login register 共用"""
        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=PrivateUserOut.model_validate(user),
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
                secret_hash=await hash_secret_async(password),
                is_verified=True,  # 密码注册视为已验证
            )
        except IdentityAlreadyTaken:
            logger.warning("register_conflict", account=account)
            raise
        logger.info("register_success", user_id=str(user.id), account=account)
        return user

    #  ---- 登录 ----

    async def _finalize_login(self, identity: AuthIdentity) -> User:
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
        # TODO(M2): 两次写库需同一事务
        await self.repo.update_identity(identity)
        user.last_login_at = now
        await self.repo.update_user(user)
        logger.info(
            "login_success", user_id=str(user.id), provider=identity.provider.value
        )
        return user

    async def login_with_password(self, *, account: str, password: str) -> User:
        """校验凭据；通过后交给 _finalize_login 处理登录副作用"""
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

        return await self._finalize_login(identity)

    #  ---- 查用户 ----

    async def get_user_public(self, user_id: UUID) -> PublicUserOut:
        """获取用户公开信息"""
        user = await self.repo.get_user_by_id(user_id)
        if user is None:
            logger.info("active_user_not_found", user_id=str(user_id))
            raise UserNotFound
        return PublicUserOut.model_validate(user)

    async def get_user_private(self, user_id: UUID) -> PrivateUserOut:
        """获取用户私密信息"""
        user = await self.repo.get_user_by_id(user_id)
        if user is None:
            logger.info("active_user_not_found", user_id=str(user_id))
            raise UserNotFound
        return PrivateUserOut.model_validate(user)

    async def get_active_user(self, user_id: UUID) -> User | None:
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            logger.info("active_user_not_found", user_id=str(user_id))
            return None
        if user.status != UserStatus.ACTIVE:
            logger.warning("active_user_disabled", user_id=str(user_id))
            return None
        return user

    # ---- Token ----
    async def resolve_active_user(self, payload: dict) -> User:
        sub = payload.get("sub")
        if sub is None:
            logger.warning("auth_failed", reson="missing_sub")
            raise AuthenticationError("无效 Token")
        try:
            user_id = UUID(sub)
        except ValueError as e:
            logger.warning("auth_failed", reason="invalid_sub_format")
            raise AuthenticationError("无效 Token") from e

        user = await self.get_active_user(user_id)
        if user is None:
            raise AuthenticationError("用户不可用")
        return user

    async def refresh_token(self, refresh_token: str) -> User:
        try:
            payload = decode_token(refresh_token, "refresh")
        except InvalidTokenError as e:
            logger.warning("refresh_failed", reason="invalid_token")
            raise AuthenticationError("Refresh Token 无效或已过期") from e
        return await self.resolve_active_user(payload)
