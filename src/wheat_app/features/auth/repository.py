# src/wheat_app/features/auth/repository.py
"""Auth 存储端口（Protocol）。

service 依赖这个协议，而不是具体实现；换数据库/测试替身时 service 不改。
实现见 ``repository_sql.py``。
"""

from typing import Protocol
from uuid import UUID

from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User


class AuthRepository(Protocol):
    """Auth 领域需要的全部持久化能力。"""

    # ---------------------------------------------------------------- 创建

    async def create_user_with_identity(
        self,
        *,
        provider: AuthProvider,
        identifier: str,
        nickname: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> User:
        """创建用户及其首条登录身份（同一事务）。"""
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
        """给已有用户绑定一条新登录身份。"""
        ...

    # ---------------------------------------------------------------- 查询

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """按主键查用户；不存在返回 ``None``。"""
        ...

    async def get_identity(
        self,
        provider: AuthProvider,
        identifier: str,
    ) -> AuthIdentity | None:
        """按 (provider, identifier) 查身份；不存在返回 ``None``。"""
        ...

    async def get_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        """查某个用户的所有登录身份；不存在返回空列表。"""
        ...

    async def get_identities_by_provider(
        self,
        provider: AuthProvider,
        identifier: str,
    ) -> AuthIdentity | None:
        """查 (provider, identifier) 是否已被占用。"""
        ...

    # ---------------------------------------------------------------- 更新

    async def update_user(self, user: User) -> User:
        """整行覆盖用户（字段白名单由 service 控制）。"""
        ...

    async def update_identity(self, identity: AuthIdentity) -> AuthIdentity:
        """整行覆盖登录身份。"""
        ...

    # ---------------------------------------------------------------- 删除

    async def delete_identity(self, identity: AuthIdentity) -> None:
        """删除一条登录身份。"""
        ...
