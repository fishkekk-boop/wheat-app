# src/wheat_app/features/auth/repository.py
"""Auth：数据存储"""

from typing import Protocol
from uuid import UUID

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

    async def add_identity(
        self,
        *,
        user_id: UUID,
        provider: AuthProvider,
        identifier: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> AuthIdentity:
        """给已有用户绑定新登录方式，原子完成"""
        ...

    #  ---- 查询 ----
    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """按主键查用户"""
        ...

    async def get_identity(
        self,
        provider: AuthProvider,
        identifier: str,
    ) -> AuthIdentity | None:
        """按 (provider, identifier) 查凭证"""
        ...

    async def get_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        """查该 id 用户的所有登录方式"""
        ...

    #  ---- 更新 ----
    async def update_user(self, user: User) -> User:
        """更新用户资料/状态"""
        ...

    async def update_identity(self, identity: AuthIdentity) -> AuthIdentity:
        """更新登录凭证"""
        ...
