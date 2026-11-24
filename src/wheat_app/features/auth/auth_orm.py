# src/wheat_app/features/auth/auth_orm.py
"""SQLAlchemy 表结构（ORM 映射）。"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wheat_app.core.database import Base, TimestampMixin
from wheat_app.features.auth.models import (
    AuthIdentity,
    AuthProvider,
    User,
    UserRole,
    UserStatus,
)

# 枚举列统一用 native_enum=False（VARCHAR + CHECK），并把 StrEnum 的 value 存进去，
# 这样数据库里是 'active' 而不是 'ACTIVE'，与领域/API 一致。
ENUM_KW = {"native_enum": False, "values_callable": lambda e: [m.value for m in e]}


class UserORM(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nickname: Mapped[str] = mapped_column(String(30))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status", **ENUM_KW),
        default=UserStatus.ACTIVE,
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", **ENUM_KW),
        default=UserRole.USER,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    identities: Mapped[list["AuthIdentityORM"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def to_domain(self) -> User:
        return User(
            id=self.id,
            nickname=self.nickname,
            avatar_url=self.avatar_url,
            bio=self.bio,
            email=self.email,
            phone=self.phone,
            status=self.status,
            role=self.role,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_login_at=self.last_login_at,
        )


class AuthIdentityORM(Base, TimestampMixin):
    __tablename__ = "auth_identities"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[AuthProvider] = mapped_column(
        SAEnum(AuthProvider, name="identity_provider", **ENUM_KW)
    )
    identifier: Mapped[str] = mapped_column(String(255))
    secret_hash: Mapped[str | None] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["UserORM"] = relationship(back_populates="identities", lazy="raise")

    __table_args__ = (
        # 全局唯一：同一个 (provider, identifier) 只能属于一个用户。
        UniqueConstraint("provider", "identifier", name="uq_auth_provider_identifier"),
        # 每用户每 provider 至多一条：一个用户只能有一个密码/邮箱/手机号身份。
        UniqueConstraint("user_id", "provider", name="uq_auth_user_provider"),
    )

    def to_domain(self) -> AuthIdentity:
        return AuthIdentity(
            id=self.id,
            user_id=self.user_id,
            provider=self.provider,
            identifier=self.identifier,
            secret_hash=self.secret_hash,
            is_verified=self.is_verified,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_used_at=self.last_used_at,
        )
