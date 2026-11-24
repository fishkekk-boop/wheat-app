from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from wheat_app.core.db_errors import get_constraint_name
from wheat_app.core.exceptions import ConflictError, EntityNotFound
from wheat_app.features.auth.auth_orm import AuthIdentityORM, UserORM
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User


class SQLAlchemyAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
            await self.session.refresh(user_orm)
            return user_orm.to_domain()
        except IntegrityError as e:
            await self.session.rollback()
            constraint = get_constraint_name(e)
            if constraint == "uq_auth_provider_identifier":
                raise ConflictError(
                    entity="AuthIdentity",
                    identifier=f"{provider}:{identifier}",
                )
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
        """给已有用户绑定新登录方式，原子完成"""
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
        except IntegrityError as e:
            await self.session.rollback()
            constraint = get_constraint_name(e)
            if constraint == "auth_identities_user_id_fkey":
                raise EntityNotFound(entity="User", entity_id=user_id)
            if constraint == "uq_auth_provider_identifier":
                raise ConflictError(
                    entity="AuthIdentity",
                    identifier=f"{provider}:{identifier}",
                )
            raise

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """按主键查用户，不存在返回 None。"""
        user = await self.session.get(UserORM, user_id)
        return user.to_domain() if user is not None else None

    async def get_identity(
        self,
        provider: AuthProvider,
        identifier: str,
    ) -> AuthIdentity | None:
        """按 (provider, identifier) 查凭证"""
        stmt = select(AuthIdentityORM).where(
            AuthIdentityORM.provider == provider,
            AuthIdentityORM.identifier == identifier,
        )
        result = await self.session.execute(stmt)
        identity_orm = result.scalar_one_or_none()
        return identity_orm.to_domain() if identity_orm is not None else None

    async def get_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        """查该 id 用户的所有登录方式，用户不存在时返回空列表"""
        stmt = select(AuthIdentityORM).where(
            AuthIdentityORM.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return [i.to_domain() for i in result.scalars().all()]

    #  ---- 更新 ----
    async def update_user(self, user: User) -> User:
        """更新用户资料/状态"""
        try:
            user_orm = await self.session.get(
                entity=UserORM, ident=user.id, with_for_update=True
            )
            if user_orm is None:
                raise EntityNotFound("User", user.id)

            user_orm.nickname = user.nickname
            user_orm.avatar_url = user.avatar_url
            user_orm.bio = user.bio
            user_orm.email = user.email
            user_orm.phone = user.phone
            user_orm.status = user.status
            user_orm.last_login_at = user.last_login_at
            await self.session.flush()
            await self.session.refresh(user_orm)
            return user_orm.to_domain()
        except IntegrityError as e:
            await self.session.rollback()
            constraint = get_constraint_name(e)
            if constraint == "users_email_key":
                raise ConflictError(
                    entity="User", identifier=f"email={user.email}"
                ) from e
            if constraint == "users_phone_key":
                raise ConflictError(
                    entity="User", identifier=f"phone={user.phone}"
                ) from e
            raise

    async def update_identity(self, identity: AuthIdentity) -> AuthIdentity:
        """更新登录凭证"""
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
        except IntegrityError as e:
            await self.session.rollback()
            constraint = get_constraint_name(e)
            if constraint == "uq_auth_provider_identifier":
                raise ConflictError(
                    entity="AuthIdentity",
                    identifier=f"{identity.provider}:{identity.identifier}",
                ) from e
            raise
