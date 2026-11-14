# src/wheat_app/features/auth/router.py
"""Auth: 路由"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from wheat_app.features.auth.dependencies import get_auth_service, get_current_user
from wheat_app.features.auth.models import User
from wheat_app.features.auth.schemas import (
    AuthResponse,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    PrivateUserOut,
    PublicUserOut,
    RefreshRequest,
    TokenPair,
)
from wheat_app.features.auth.service import AuthService, AuthSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register/password",
    response_model=AuthResponse,
    status_code=201,
    summary="注册（用户名+密码）",
)
async def register_with_password(
    body: PasswordRegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSession:

    user = await service.register_with_password(
        account=body.account, password=body.password, nickname=body.nickname
    )
    return service.issue_session(user)


@router.post(
    "/login/password/form", response_model=AuthResponse, include_in_schema=False
)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSession:
    user = await service.login_with_password(
        account=form.username,
        password=form.password,
    )
    return service.issue_session(user)


@router.post(
    "/login/password",
    response_model=AuthResponse,
    status_code=200,
    summary="登录（用户名+密码）",
)
async def login_with_password(
    body: PasswordLoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSession:

    user = await service.login_with_password(
        account=body.account, password=body.password
    )
    return service.issue_session(user)


@router.get(
    "/users/me",
    response_model=PrivateUserOut,
    status_code=200,
    summary="查询当前用户",
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@router.get(
    "/users/{user_id}",
    response_model=PublicUserOut,
    status_code=200,
    summary="查询用户公开资料",
)
async def user_info(
    user_id: UUID, service: Annotated[AuthService, Depends(get_auth_service)]
) -> User:
    return await service.get_user(user_id)


@router.post(
    "/token/refresh",
    response_model=TokenPair,
    status_code=200,
    summary="刷新 Access + Refresh Token",
)
async def refresh_tokens(
    body: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSession:
    return await service.refresh_session(body.refresh_token)
