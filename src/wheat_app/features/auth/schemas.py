# src/wheat_app/features/auth/schemas.py
"""Auth 的 HTTP 请求/响应模型（传输层契约）。"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from wheat_app.features.auth.models import AuthProvider, UserRole, UserStatus
from wheat_app.shared.constraints import StrippedStr
from wheat_app.shared.schema import ORMModel

# 登录账号：3-20 位，仅字母/数字/下划线。
Account = Annotated[
    StrippedStr, Field(min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
]

# 昵称。
Nickname = Annotated[StrippedStr, Field(min_length=1, max_length=30)]


# ---------------------------------------------------------------- 请求


class PasswordRegisterRequest(BaseModel):
    account: Account
    password: Annotated[str, Field(min_length=8, max_length=128)]
    nickname: Nickname | None = None


class PasswordLoginRequest(BaseModel):
    account: Account
    password: Annotated[str, Field(min_length=1, max_length=128)]


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    """只允许改这三项；email / phone / status / role 不能从这里改。"""

    nickname: Nickname | None = None
    avatar_url: Annotated[str, Field(max_length=500)] | None = None
    bio: Annotated[str, Field(max_length=500)] | None = None


class UnbindIdentityRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]


# ---------------------------------------------------------------- 响应


class PublicUserOut(ORMModel):
    """公开资料：匿名可见，绝不能包含 email / phone。"""

    nickname: str
    avatar_url: str | None
    bio: str | None
    status: UserStatus
    role: UserRole


class PrivateUserOut(PublicUserOut):
    """私密资料：仅本人可见。"""

    id: UUID
    email: str | None
    phone: str | None
    created_at: datetime
    last_login_at: datetime | None


class AuthResponse(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: PrivateUserOut


class TokenPair(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class IdentityOut(ORMModel):
    """当前用户的单条登录方式（不暴露 secret_hash）。"""

    provider: AuthProvider
    identifier: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
