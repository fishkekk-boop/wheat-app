# src/wheat_app/features/auth/router.py
"""Auth: 路由"""

from typing import Annotated

from fastapi import APIRouter, Depends

from wheat_app.features.auth.dependencies import get_auth_service
from wheat_app.features.auth.schemas import (
    AuthResponse,
    PasswordLoginRequest,
    PasswordRegisterRequest,
)
from wheat_app.features.auth.service import AuthService

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
) -> AuthResponse:

    user = await service.register_with_password(
        account=body.account, password=body.password, nickname=body.nickname
    )
    return service.build_auth_response(user)


@router.post(
    "/login/password",
    response_model=AuthResponse,
    status_code=200,
    summary="注册（登录+密码）",
)
async def login_with_password(
    body: PasswordLoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:

    user = await service.login_with_password(
        account=body.account, password=body.password
    )
    return service.build_auth_response(user)
