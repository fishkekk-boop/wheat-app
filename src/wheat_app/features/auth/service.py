# src/wheat_app/features/auth/service.py
"""Auth 业务逻辑（用例编排层）。"""

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
    IdentifierAlreadyBound,
    IdentityAlreadyTaken,
    IdentityNotFound,
    LastIdentityRequired,
    ProviderAlreadyBound,
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
    """一次认证会话的领域结果：谁 + 一对新 token。"""

    user: User
    access_token: str
    refresh_token: str


class AuthService:
    _DEFAULT_NICKNAME_PREFIX = "麦田用户"

    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo

    # ---------------------------------------------------------------- 辅助

    def _generate_default_nickname(self) -> str:
        return f"{self._DEFAULT_NICKNAME_PREFIX}_{secrets.token_hex(3)}"

    def issue_session(self, user: User) -> AuthSession:
        """为已认证用户签发一对 token。"""
        return AuthSession(
            user=user,
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    @staticmethod
    def _find_identity(
        identities: list[AuthIdentity], provider: AuthProvider
    ) -> AuthIdentity | None:
        return next((i for i in identities if i.provider is provider), None)

    # ---------------------------------------------------------------- 注册

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
        except ConflictError as exc:
            raise IdentityAlreadyTaken() from exc

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

    # ---------------------------------------------------------------- 登录

    async def _complete_login(self, identity: AuthIdentity) -> User:
        """登录校验通过后：加载用户、检查状态、更新审计字段。"""
        user = await self.repo.get_user_by_id(identity.user_id)
        if user is None:
            logger.warning(
                "login_failed", identity_id=str(identity.id), reason="user_missing"
            )
            raise InvalidCredentials()
        if user.status is not UserStatus.ACTIVE:
            logger.warning(
                "login_failed", identity_id=str(identity.id), reason="inactive_user"
            )
            raise InvalidCredentials()

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
        logger.info("login_attempt", provider="password", identifier=account)
        identity = await self.repo.get_identity(AuthProvider.PASSWORD, account)

        # 账号不存在时也做一次哈希比对，避免响应时间差被用来枚举账号。
        if identity is None or not identity.secret_hash:
            await verify_password_async(password, DUMMY_HASH)
            logger.warning(
                "login_failed", identifier=account, reason="invalid_credentials"
            )
            raise InvalidCredentials()

        if not await verify_password_async(password, identity.secret_hash):
            logger.warning(
                "login_failed", identifier=account, reason="invalid_credentials"
            )
            raise InvalidCredentials()

        return await self._complete_login(identity)

    # ---------------------------------------------------------------- 查询

    async def _load_user(self, user_id: UUID) -> User:
        user = await self.repo.get_user_by_id(user_id)
        if user is None:
            raise UserNotFound()
        return user

    async def get_user(self, user_id: UUID) -> User:
        """按 id 查用户；不存在抛 UserNotFound（404）。"""
        return await self._load_user(user_id)

    async def require_active_user(self, user_id: UUID) -> User:
        """认证用：用户必须存在且 ACTIVE，否则 401。"""
        user = await self._load_user(user_id)
        if user.status is not UserStatus.ACTIVE:
            raise UserDisabled()
        return user

    async def user_from_token_payload(self, payload: dict) -> User:
        """把已解码的 token payload 还原成可用用户；任何失败一律 401。"""
        sub = payload.get("sub")
        if sub is None:
            logger.warning("auth_failed", reason="missing_sub")
            raise AuthenticationError()
        try:
            user_id = UUID(sub)
        except ValueError as exc:
            logger.warning("auth_failed", reason="invalid_sub_format")
            raise AuthenticationError() from exc

        try:
            return await self.require_active_user(user_id)
        except UserNotFound as exc:
            raise AuthenticationError() from exc

    async def get_user_identities(self, user_id: UUID) -> list[AuthIdentity]:
        return await self.repo.get_identities_by_user_id(user_id)

    # ---------------------------------------------------------------- 更新

    async def update_user_profile(
        self,
        *,
        user: User,
        nickname: str | None,
        bio: str | None,
        avatar_url: str | None,
    ) -> User:
        """更新本人资料；只允许改 nickname / bio / avatar_url。"""
        if nickname is not None:
            user.nickname = nickname
        if bio is not None:
            user.bio = bio
        if avatar_url is not None:
            user.avatar_url = avatar_url

        logger.info("update_user_profile_success", user_id=str(user.id))
        return await self.repo.update_user(user)

    # ---------------------------------------------------------------- 绑定 / 解绑

    async def bind_identifier(
        self,
        *,
        user: User,
        provider: AuthProvider,
        identifier: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> AuthIdentity:
        """给当前用户绑定一条新登录方式。

        业务规则：
        - 该 (provider, identifier) 全局唯一（被别的账号占用则拒绝）
        - 同一用户同一 provider 只能有一条
        """
        if await self.repo.get_identities_by_provider(provider, identifier):
            logger.warning("bind_identity_failed", reason="identifier_taken")
            raise IdentifierAlreadyBound()

        identities = await self.repo.get_identities_by_user_id(user.id)
        if self._find_identity(identities, provider) is not None:
            logger.warning("bind_identity_failed", reason="provider_bound")
            raise ProviderAlreadyBound()

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
        """解绑一条登录方式；需重新输入密码。"""
        identities = await self.repo.get_identities_by_user_id(user.id)

        target = self._find_identity(identities, provider)
        if target is None:
            raise IdentityNotFound(provider)

        password_identity = self._find_identity(identities, AuthProvider.PASSWORD)
        if password_identity is None or not await verify_password_async(
            current_password, password_identity.secret_hash or ""
        ):
            raise InvalidCredentials()
        valid_identity = next((i for i in identities if i.is_verified == True), None)
        if len(identities) <= 1 and valid_identity is not None:
            raise LastIdentityRequired()

        await self.repo.delete_identity(target)

    # ---------------------------------------------------------------- Token

    async def refresh_session(self, token: str) -> AuthSession:
        """校验 refresh token，签发新的一对 token。"""
        try:
            payload = decode_token(token, "refresh")
        except InvalidTokenError as exc:
            logger.warning("refresh_failed", reason="invalid_token")
            raise AuthenticationError() from exc

        user = await self.user_from_token_payload(payload)
        return self.issue_session(user)

    # ---------------------------------------------------------------- 删除

    async def delete_user(self, user_id: UUID, operator: User) -> None:
        """软删除用户（仅管理员）。"""
        if operator.role is not UserRole.ADMIN:
            logger.warning("delete_user_failed", reason="forbidden")
            raise Forbidden()
        if operator.id == user_id:
            raise Forbidden("不能删除自己")

        user = await self.get_user(user_id)
        user.status = UserStatus.DELETED
        identities = await self.get_user_identities(user_id)
        for i in identities:
            i.identifier = f"{i.identifier}_deleted_{i.id}"
            await self.repo.update_identity(i)
        await self.repo.update_user(user)
        logger.info("delete_user_success", operator=operator.id, deleted=user_id)
