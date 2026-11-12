# src/wheat_app/features/auth/ dependencies.py
"""Auth：依赖"""

from typing import Annotated

from fastapi import Depends, Request

from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.service import AuthService


def get_auth_repo(request: Request) -> AuthRepository:
    return request.app.state.auth_repo


def get_auth_service(
    repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> AuthService:
    return AuthService(repo)
