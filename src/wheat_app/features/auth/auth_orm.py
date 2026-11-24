import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wheat_app.core.database import Base, TimestampMixin
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User, UserStatus


class UserORM(Base, TimestampMixin):
    """用户模型"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nickname: Mapped[str] = mapped_column(String(30), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(254),
        unique=True,
        index=True,
        nullable=True,
    )
    phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=True,
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(
            UserStatus,
            name="user_status",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    identities: Mapped[list["AuthIdentityORM"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<UserORM id={self.id} nickname={self.nickname!r}>"

    def to_domain(self) -> User:
        return User(
            id=self.id,
            nickname=self.nickname,
            avatar_url=self.avatar_url,
            bio=self.bio,
            email=self.email,
            phone=self.phone,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_login_at=self.last_login_at,
        )


class AuthIdentityORM(Base, TimestampMixin):
    """身份认证模型"""

    __tablename__ = "auth_identities"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[AuthProvider] = mapped_column(
        SAEnum(
            AuthProvider,
            name="identity_provider",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    user: Mapped["UserORM"] = relationship(
        back_populates="identities",
        lazy="raise",
    )
    __table_args__ = (
        UniqueConstraint("provider", "identifier", name="uq_auth_provider_identifier"),
    )

    def to_domain(self) -> AuthIdentity:
        return AuthIdentity(
            id=self.id,
            user_id=self.user_id,
            provider=AuthProvider(self.provider),
            identifier=self.identifier,
            secret_hash=self.secret_hash,
            is_verified=self.is_verified,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_used_at=self.last_used_at,
        )
