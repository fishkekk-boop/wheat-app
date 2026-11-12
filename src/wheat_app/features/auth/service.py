# src/wheat_app/features/auth/service.py
"""Auth: 业务异常 + 业务逻辑"""

import secrets
from datetime import UTC, datetime

import structlog

from wheat_app.core.exceptions import ConflictError, InvalidCredentials
from wheat_app.core.security import DUMMY_HASH, hash_secret_async, verify_password_async
from wheat_app.features.auth.exceptions import IdentityAlreadyTaken
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User, UserStatus
from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.schemas import (
    AuthResponse,
    UserOut,
)
from wheat_app.features.auth.tokens import create_access_token, create_refresh_token

logger = structlog.get_logger(__name__)


class AuthService:
    _DEFAULT_NICKNAME_PREFIX = "麦田用户"

    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo

    def _generate_default_nickname(self) -> str:
        return f"{self._DEFAULT_NICKNAME_PREFIX}_{secrets.token_hex(3)}"

    def build_auth_response(self, user: User) -> AuthResponse:
        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserOut.model_validate(user),
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
