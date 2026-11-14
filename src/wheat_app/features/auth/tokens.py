from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import structlog
from jwt.exceptions import InvalidTokenError

from wheat_app.config import get_settings

logger = structlog.get_logger(__name__)


def _create_token(
    user_id: UUID, token_type: str, expires_delta: timedelta, scope: str | None = None
) -> str:
    now = datetime.now(UTC)
    settings = get_settings()
    payload = {
        "sub": str(user_id),  # 用户标识
        "type": token_type,  # token 类型，decode 时校验
        "iat": now,  # 签发时间
        "exp": now + expires_delta,
        "jti": uuid4().hex,  # 唯一 ID，未来做黑名单/撤销用
    }
    if scope is not None:
        payload["scope"] = scope

    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def create_access_token(user_id: UUID, scope: str = "full") -> str:
    settings = get_settings()
    return _create_token(
        user_id=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        scope=scope,
    )


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()

    return _create_token(
        user_id=user_id,
        token_type="refresh",
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
    )


def decode_token(token: str, expected_type) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
        )
        print(payload)
    except InvalidTokenError:
        logger.warning("decode_failed", reason="jwt decode failed")
        raise
    if payload.get("type") != expected_type:
        logger.info("decode_failed", expected_type=expected_type)
        raise InvalidTokenError(f"Expected {expected_type} token")
    return payload
