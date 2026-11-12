# src/wheat_app/features/auth/repository.py
"""Auth：数据存储"""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from wheat_app.core.exceptions import ConflictError
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User


class AuthRepository(Protocol):
    # ---- 创建（聚合原子操作）----
    async def create_user_with_identity(
        self,
        *,
        provider: AuthProvider,
        identifier: str,
        nickname: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> User:
        """创建 User + 首条 AuthIdentity，原子完成"""
        ...

    # async def add_identity(
    #     self,
    #     *,
    #     user_id: UUID,
    #     provider: AuthProvider,
    #     identifier: str,
    #     secret_hash: str | None = None,
    #     is_verified: bool = False,
    # ) -> AuthIdentity:
    #     """给已有用户绑定新登录方式，原子完成"""
    #     ...

    # # ---- 查询 ----
    # async def get_user_by_id(self, user_id: UUID) -> User | None:
    #     """按主键查用户"""
    #     ...

    # async def get_identity(
    #     self,
    #     provider: AuthProvider,
    #     identifier: str,
    # ) -> AuthIdentity | None:
    #     """按 (provider, identifier) 查凭证"""
    #     ...

    # async def get_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
    #     """查该 id 用户的所有登录方式"""
    #     ...

    # # ---- 更新 ----
    # async def update_user(self, user: User) -> User:
    #     """更新用户资料/状态"""
    #     ...

    # async def update_identity(self, identity: AuthIdentity) -> AuthIdentity:
    #     """更新登录凭证"""
    #     ...


class InMemoryAuthRepository:
    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}
        self._identities: dict[UUID, AuthIdentity] = {}
        self._identity_index: dict[tuple[AuthProvider, str], UUID] = {}

    async def create_user_with_identity(
        self,
        *,
        provider: AuthProvider,
        identifier: str,
        nickname: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> User:
        """创建 User + 首条 AuthIdentity，原子完成"""
        key = (provider, identifier)
        if key in self._identity_index:
            raise ConflictError(
                entity="AuthIdentity", identifier=f"{provider}:{identifier}"
            )
        now = datetime.now(UTC)
        user = User(
            id=uuid4(),
            nickname=nickname,
            created_at=now,
            updated_at=now,
        )
        auth_identity = AuthIdentity(
            id=uuid4(),
            user_id=user.id,
            provider=provider,
            identifier=identifier,
            secret_hash=secret_hash,
            is_verified=is_verified,
            created_at=now,
            updated_at=now,
        )
        self._users[user.id] = user
        self._identities[auth_identity.id] = auth_identity
        self._identity_index[key] = auth_identity.id
        return user

    # async def add_identity(
    #     self,
    #     *,
    #     user_id: UUID,
    #     provider: AuthProvider,
    #     identifier: str,
    #     secret_hash: str | None = None,
    #     is_verified: bool = False,
    # ) -> AuthIdentity:
    #     """给已有用户绑定新登录方式，原子完成"""

    # # ---- 查询 ----
    # async def get_user_by_id(self, user_id: UUID) -> User | None:
    #     """按主键查用户"""

    # async def get_identity(
    #     self,
    #     provider: AuthProvider,
    #     identifier: str,
    # ) -> AuthIdentity | None:
    #     """按 (provider, identifier) 查凭证"""

    # async def get_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
    #     """查该 id 用户的所有登录方式"""

    # # ---- 更新 ----
    # async def update_user(self, user: User) -> User:
    #     """更新用户资料/状态"""

    # async def update_identity(self, identity: AuthIdentity) -> AuthIdentity:
    #     """更新登录凭证"""
