# src/wheat_app/features/auth/models.py
"""Auth 领域模型（纯 Pydantic，不依赖数据库/传输层）。"""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from wheat_app.shared.constraints import PhoneNumber, StrippedStr


class UserStatus(StrEnum):
    """账号状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class UserRole(StrEnum):
    """用户角色，数值越大权限越高。"""

    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"

    @property
    def level(self) -> int:
        return _ROLE_LEVELS[self.value]


_ROLE_LEVELS = {"user": 1, "premium": 2, "admin": 99}


class AuthProvider(StrEnum):
    """登录方式。"""

    PASSWORD = "password"
    EMAIL = "email"
    PHONE = "phone"


class User(BaseModel):
    id: UUID
    nickname: Annotated[StrippedStr, Field(min_length=1, max_length=30)]
    avatar_url: Annotated[str, Field(max_length=500)] | None = None
    bio: Annotated[str, StringConstraints(max_length=500)] | None = None
    email: EmailStr | None = None
    phone: PhoneNumber | None = None
    status: UserStatus = UserStatus.ACTIVE
    role: UserRole = UserRole.USER
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_login_at: AwareDatetime | None = None


class AuthIdentity(BaseModel):
    """一条登录凭证（user 与 provider/identifier 是多对一关系）。"""

    id: UUID
    user_id: UUID
    provider: AuthProvider
    identifier: Annotated[str, Field(min_length=1, max_length=255)]
    secret_hash: Annotated[str, Field(max_length=255)] | None = None
    is_verified: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_used_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _password_requires_secret_hash(self) -> "AuthIdentity":
        if self.provider is AuthProvider.PASSWORD and not self.secret_hash:
            raise ValueError("password 登录方式必须提供 secret_hash")
        return self
