# src/wheat_app/features/auth/ dependencies.py
"""Auth：依赖"""

from typing import Annotated

import structlog
from fastapi import Depends, Request
from jwt.exceptions import InvalidTokenError

from wheat_app.core.exceptions import AuthenticationError
from wheat_app.core.security import oauth2_scheme
from wheat_app.features.auth.models import User
from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.service import AuthService
from wheat_app.features.auth.tokens import decode_token

logger = structlog.get_logger(__name__)


def get_auth_repo(request: Request) -> AuthRepository:
    """从 app.state 取 repo，而非模块级单例。

    每个 create_app() 拥有独立存储：
    - 测试：每个 fixture 一份空 repo，测试间不串数据
    - 生产：单进程一份，随 app 生命周期创建/释放

    repo 由 lifespan 在启动时写入 app.state。
    """
    return request.app.state.auth_repo


def get_auth_service(
    repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> AuthService:
    return AuthService(repo)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """解码 Access Token 返回当前用户"""
    try:
        payload = decode_token(
            token,
            "access",
        )
    except InvalidTokenError as e:
        logger.warning("auth_failed", reason="invalid_token")
        raise AuthenticationError("Access Token 无效或已过期") from e

    return await service.user_from_token_payload(payload)
