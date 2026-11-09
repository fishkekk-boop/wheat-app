# src/wheat_app/features/auth/models.py
"""Auth：领域模型"""

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
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class AuthProvider(StrEnum):
    # 未来扩展：PHONE / EMAIL ...
    PASSWORD = "password"


class User(BaseModel):
    id: UUID
    nickname: Annotated[StrippedStr, Field(min_length=1, max_length=30)]
    avatar_url: Annotated[str, Field(max_length=500)] | None = None
    bio: Annotated[str, StringConstraints(max_length=500)] | None = None
    email: EmailStr | None = None
    phone: PhoneNumber | None = None
    status: UserStatus = UserStatus.ACTIVE
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_login_at: AwareDatetime | None = None


class AuthIdentity(BaseModel):
    id: UUID
    user_id: UUID
    provider: AuthProvider  # 登录方式枚举
    identifier: Annotated[
        str, Field(min_length=1, max_length=255)
    ]  # 该 provider 下的唯一标识。
    secret_hash: Annotated[str, Field(max_length=255)] | None = None
    is_verified: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_used_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _password_requires_secret(self) -> "AuthIdentity":
        if self.provider == AuthProvider.PASSWORD and not (
            self.secret_hash and self.secret_hash.strip()
        ):
            raise ValueError("password provider 必须提供 secret_hash")
        return self
