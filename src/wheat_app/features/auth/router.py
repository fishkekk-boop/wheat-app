# src/wheat_app/features/auth/router.py
"""Auth: 路由"""

from typing import Annotated

from fastapi import APIRouter, Depends

from wheat_app.features.auth.dependencies import get_auth_service
from wheat_app.features.auth.schemas import (
    PasswordRegisterRequest,
    RegisterResponse,
)
from wheat_app.features.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register/password", response_model=RegisterResponse, status_code=201, summary=""
)
async def register_with_password(
    body: PasswordRegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegisterResponse:

    user = await service.register_with_password(
        account=body.account, password=body.password, nickname=body.nickname
    )
    return service.build_register_response(user)
