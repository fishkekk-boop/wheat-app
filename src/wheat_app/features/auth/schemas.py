# src/wheat_app/features/auth/schemas.py
"""Auth：请求/响应模型"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from wheat_app.shared.constraints import StrippedStr
from wheat_app.shared.schema import ORMModel

from .models import UserStatus

# 用户名称
Account = Annotated[
    StrippedStr, Field(min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
]

# 密码
# Password = Annotated[str, Field(min_length=8, max_length=128)]

# 用户昵称
Nickname = Annotated[StrippedStr, Field(min_length=1, max_length=30)]


class PasswordRegisterRequest(BaseModel):
    account: Account
    password: Annotated[str, Field(min_length=8, max_length=128)]
    nickname: Nickname | None = None


class PasswordLoginRequest(BaseModel):
    account: Account
    password: Annotated[str, Field(min_length=1, max_length=128)]


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: UUID
    nickname: str
    avatar_url: str | None
    bio: str | None
    email: str | None
    phone: str | None
    status: UserStatus
    created_at: datetime
    last_login_at: datetime | None


class AuthResponse(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
