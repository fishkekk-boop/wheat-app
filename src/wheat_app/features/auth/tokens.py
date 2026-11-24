# src/wheat_app/features/auth/tokens.py
"""JWT 的签发与校验。"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import structlog
from jwt.exceptions import InvalidTokenError

from wheat_app.config import get_settings

logger = structlog.get_logger(__name__)


def _encode(user_id: UUID, *, token_type: str, expires_delta: timedelta) -> str:
    """签发一枚 token；``type`` 用于校验 access / refresh 不被混用。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid4().hex,  # 未来做撤销/黑名单用
    }
    settings = get_settings()
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    return _encode(
        user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()
    return _encode(
        user_id,
        token_type="refresh",
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
    )


def decode_token(token: str, expected_type: str) -> dict:
    """校验签名并返回 payload；类型不符抛 ``InvalidTokenError``。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            key=settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
        )
    except InvalidTokenError:
        logger.warning("decode_failed", reason="jwt_decode_failed")
        raise

    if payload.get("type") != expected_type:
        logger.warning("decode_failed", expected_type=expected_type)
        raise InvalidTokenError(f"expected {expected_type} token")
    return payload
