# src/wheat_app/features/auth/dependencies.py
"""Auth 的依赖注入（把存储/服务/当前用户接进路由）。"""

from typing import Annotated

import structlog
from fastapi import Depends
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from wheat_app.core.dependencies import get_db
from wheat_app.core.exceptions import AuthenticationError
from wheat_app.core.security import oauth2_scheme
from wheat_app.features.auth.models import User
from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.repository_sql import SQLAlchemyAuthRepository
from wheat_app.features.auth.service import AuthService
from wheat_app.features.auth.tokens import decode_token

logger = structlog.get_logger(__name__)


def get_auth_repo(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthRepository:
    """构造 SQL 仓库；session 由请求级依赖管理事务。"""
    return SQLAlchemyAuthRepository(session)


def get_auth_service(
    repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> AuthService:
    return AuthService(repo)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """从 Bearer token 还原当前用户；凭证无效/过期/用户不可用均 401。"""
    try:
        payload = decode_token(token, "access")
    except InvalidTokenError as exc:
        logger.warning("auth_failed", reason="invalid_token")
        raise AuthenticationError() from exc

    return await service.user_from_token_payload(payload)
