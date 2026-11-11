from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from wheat_app.config import get_settings


def create_access_token(user_id: UUID, scope: str = "full") -> str:
    now = datetime.now(UTC)
    settings = get_settings()
    payload = {
        "sub": str(user_id),  # 用户标识
        "type": "access",  # token 类型，decode 时校验
        "scope": scope,  # 权限范围，当前固定 "full"
        "iat": now,  # 签发时间
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": uuid4().hex,  # 唯一 ID，未来做黑名单/撤销用
    }
    return jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm
    )


def create_refresh_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_minutes),
        "jti": uuid4().hex,
    }
    return jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm
    )
