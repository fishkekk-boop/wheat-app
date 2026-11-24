# src/wheat_app/features/auth/router.py
"""Auth 的 HTTP 路由（只做参数绑定与响应形状，不含业务逻辑）。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from wheat_app.features.auth.dependencies import get_auth_service, get_current_user
from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User
from wheat_app.features.auth.schemas import (
    AuthResponse,
    IdentityOut,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    PrivateUserOut,
    ProfileUpdateRequest,
    PublicUserOut,
    RefreshRequest,
    TokenPair,
    UnbindIdentityRequest,
)
from wheat_app.features.auth.service import AuthService, AuthSession

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------- 注册 / 登录


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
    "/login/password",
    response_model=AuthResponse,
    status_code=200,
    summary="登录（用户名+密码）",
)
async def login_with_password(
    body: PasswordLoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSession:
    user = await service.login_with_password(account=body.account, password=body.password)
    return service.issue_session(user)


@router.post(
    "/login/password/form",
    response_model=AuthResponse,
    include_in_schema=False,
)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSession:
    """供 Swagger「Authorize」按钮使用的 OAuth2 form 登录。"""
    user = await service.login_with_password(
        account=form.username, password=form.password
    )
    return service.issue_session(user)


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


# ---------------------------------------------------------------- 当前用户


@router.get(
    "/users/me",
    response_model=PrivateUserOut,
    status_code=200,
    summary="查询当前用户",
)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.get(
    "/users/me/identities",
    response_model=list[IdentityOut],
    status_code=200,
    summary="查询当前用户的所有登录方式",
)
async def list_my_identities(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[AuthIdentity]:
    return await service.get_user_identities(current_user.id)


@router.patch(
    "/users/me",
    response_model=PrivateUserOut,
    status_code=200,
    summary="更新当前用户资料",
)
async def update_my_profile(
    body: ProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    return await service.update_user_profile(
        user=current_user,
        nickname=body.nickname,
        bio=body.bio,
        avatar_url=body.avatar_url,
    )


@router.delete(
    "/users/me/identities/{provider}",
    status_code=204,
    summary="解绑当前用户的某条登录方式",
)
async def unbind_my_identity(
    provider: AuthProvider,
    body: UnbindIdentityRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await service.unbind_identifier(
        user=current_user, provider=provider, current_password=body.current_password
    )


# ---------------------------------------------------------------- 公开 / 管理


@router.get(
    "/users/{user_id}",
    response_model=PublicUserOut,
    status_code=200,
    summary="查询用户公开资料",
)
async def get_user_info(
    user_id: UUID,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    return await service.get_user(user_id)


@router.delete(
    "/users/{user_id}",
    status_code=204,
    summary="删除用户（软删除，仅管理员）",
)
async def delete_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await service.delete_user(user_id, current_user)
