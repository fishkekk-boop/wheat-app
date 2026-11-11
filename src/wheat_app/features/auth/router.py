# src/wheat_app/features/auth/router.py
"""Auth: 路由"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from wheat_app.features.auth.dependencies import get_auth_service
from wheat_app.features.auth.models import User
from wheat_app.features.auth.schemas import (
    PasswordRegisterRequest,
    RegisterResponse,
    UserOut,
)
from wheat_app.features.auth.service import AuthService
from wheat_app.features.auth.tokens import create_access_token, create_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_register_response(user: User) -> RegisterResponse:
    return RegisterResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post(
    "/register/password", response_model=RegisterResponse, status_code=201, summary=""
)
async def register_with_password(
    body: PasswordRegisterRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegisterResponse:

    user = await service.register_with_password(
        account=body.account, password=body.password, nickname=body.nickname
    )
    response.headers["Location"] = f"/users/{user.id}"
    return _build_register_response(user)
