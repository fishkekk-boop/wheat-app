# src/wheat_app/core/dependencies.py
"""全局依赖：get_db、分页、当前用户"""

from typing import Annotated

import structlog
from fastapi import Depends
from jwt.exceptions import InvalidTokenError

from wheat_app.core.exceptions import AuthenticationError
from wheat_app.core.security import oauth2_scheme
from wheat_app.features.auth.dependencies import get_auth_service
from wheat_app.features.auth.models import User
from wheat_app.features.auth.service import AuthService
from wheat_app.features.auth.tokens import decode_token

logger = structlog.get_logger(__name__)


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

    return await service.resolve_active_user(payload)
