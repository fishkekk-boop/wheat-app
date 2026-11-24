# src/wheat_app/features/auth/repository_sql.py
"""SQLAlchemy 版仓库（适配器）。

事务约定
--------
- 正常路径：只 ``add`` / ``flush``，**不提交**；由 ``core.dependencies.get_db``
  在请求结束时统一 commit / rollback。
- ``flush()`` 会把唯一约束/外键约束错误提前抛到本层，从而能被翻译成业务异常
  （否则会延迟到请求结束的 commit，客户端只能拿到 500）。
- 捕获 ``IntegrityError`` 后本层会 ``rollback()`` 再翻译成业务异常；
  这意味着该请求内的其它写也会被回滚——当前每个用例都是单步写，可接受。
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from wheat_app.core.db_errors import get_constraint_name
from wheat_app.core.exceptions import ConflictError, EntityNotFound
from wheat_app.features.auth.auth_orm import AuthIdentityORM, UserORM
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User


class SQLAlchemyAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        """创建用户及其首条身份，同一事务内完成。"""
        try:
            user_orm = UserORM(nickname=nickname)
            self.session.add(user_orm)
            await self.session.flush()

            identity_orm = AuthIdentityORM(
                user_id=user_orm.id,
                provider=provider,
                identifier=identifier,
                secret_hash=secret_hash,
                is_verified=is_verified,
            )
            self.session.add(identity_orm)
            await self.session.flush()
            await self.session.refresh(user_orm)  # 载入 created_at/updated_at
            return user_orm.to_domain()
        except IntegrityError as exc:
            await self.session.rollback()
            if get_constraint_name(exc) == "uq_auth_provider_identifier":
                raise ConflictError(
                    entity="AuthIdentity", identifier=f"{provider.value}:{identifier}"
                ) from exc
            raise

    async def add_identity(
        self,
        *,
        user_id: UUID,
        provider: AuthProvider,
        identifier: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> AuthIdentity:
        """给已有用户绑定一条新身份。"""
        try:
            identity_orm = AuthIdentityORM(
                user_id=user_id,
                provider=provider,
                identifier=identifier,
                secret_hash=secret_hash,
                is_verified=is_verified,
            )
            self.session.add(identity_orm)
            await self.session.flush()
            await self.session.refresh(identity_orm)
            return identity_orm.to_domain()
        except IntegrityError as exc:
            await self.session.rollback()
            constraint = get_constraint_name(exc)
            if constraint == "auth_identities_user_id_fkey":
                raise EntityNotFound(entity="User", entity_id=user_id) from exc
            if constraint in ("uq_auth_provider_identifier", "uq_auth_user_provider"):
                raise ConflictError(
                    entity="AuthIdentity", identifier=f"{provider.value}:{identifier}"
                ) from exc
            raise

    # ---------------------------------------------------------------- 查询

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        user = await self.session.get(UserORM, user_id)
        return user.to_domain() if user is not None else None

    async def get_identity(
        self,
        provider: AuthProvider,
        identifier: str,
    ) -> AuthIdentity | None:
        stmt = select(AuthIdentityORM).where(
            AuthIdentityORM.provider == provider,
            AuthIdentityORM.identifier == identifier,
        )
        identity = (await self.session.execute(stmt)).scalar_one_or_none()
        return identity.to_domain() if identity is not None else None

    async def get_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        stmt = select(AuthIdentityORM).where(AuthIdentityORM.user_id == user_id)
        result = await self.session.execute(stmt)
        return [row.to_domain() for row in result.scalars().all()]

    async def get_identities_by_provider(
        self,
        provider: AuthProvider,
        identifier: str,
    ) -> AuthIdentity | None:
        """查 (provider, identifier) 是否已被占用。"""
        return await self.get_identity(provider, identifier)

    # ---------------------------------------------------------------- 更新

    async def update_user(self, user: User) -> User:
        """整行覆盖用户。"""
        try:
            user_orm = await self.session.get(UserORM, user.id, with_for_update=True)
            if user_orm is None:
                raise EntityNotFound("User", user.id)

            user_orm.nickname = user.nickname
            user_orm.avatar_url = user.avatar_url
            user_orm.bio = user.bio
            user_orm.email = user.email
            user_orm.phone = user.phone
            user_orm.status = user.status
            user_orm.role = user.role
            user_orm.last_login_at = user.last_login_at
            await self.session.flush()
            await self.session.refresh(user_orm)
            return user_orm.to_domain()
        except IntegrityError as exc:
            await self.session.rollback()
            # email/phone 是 unique=True + index=True，Postgres 里生成的是**唯一索引**
            # （users_email_idx）；若将来改成显式 UniqueConstraint 则叫 users_email_key。
            constraint = get_constraint_name(exc)
            if constraint in ("users_email_idx", "users_email_key"):
                raise ConflictError(
                    entity="User", identifier=f"email={user.email}"
                ) from exc
            if constraint in ("users_phone_idx", "users_phone_key"):
                raise ConflictError(
                    entity="User", identifier=f"phone={user.phone}"
                ) from exc
            raise

    async def update_identity(self, identity: AuthIdentity) -> AuthIdentity:
        """整行覆盖登录身份。"""
        try:
            identity_orm = await self.session.get(AuthIdentityORM, identity.id)
            if identity_orm is None:
                raise EntityNotFound("AuthIdentity", identity.id)

            identity_orm.provider = identity.provider
            identity_orm.identifier = identity.identifier
            identity_orm.secret_hash = identity.secret_hash
            identity_orm.is_verified = identity.is_verified
            identity_orm.last_used_at = identity.last_used_at
            await self.session.flush()
            await self.session.refresh(identity_orm)
            return identity_orm.to_domain()
        except IntegrityError as exc:
            await self.session.rollback()
            if get_constraint_name(exc) == "uq_auth_provider_identifier":
                raise ConflictError(
                    entity="AuthIdentity",
                    identifier=f"{identity.provider.value}:{identity.identifier}",
                ) from exc
            raise

    # ---------------------------------------------------------------- 删除

    async def delete_identity(self, identity: AuthIdentity) -> None:
        stmt = delete(AuthIdentityORM).where(AuthIdentityORM.id == identity.id)
        await self.session.execute(stmt)
