# tests/test_auth_profile.py
"""用户资料 / Token 刷新 的集成测试。

守三条线：
  1. 认证边界：`/users/me` 必须带 access token；`/users/{id}` 允许匿名
  2. 字段边界：公开资料绝不能带 email / phone（新增字段时这条会立刻红）
  3. token 类型：access 与 refresh 不能互相顶替
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from wheat_app.config import get_settings
from wheat_app.features.auth.models import AuthProvider, UserStatus

REGISTER_URL = "/auth/register/password"
ME_URL = "/auth/users/me"
REFRESH_URL = "/auth/token/refresh"

PUBLIC_KEYS = {"nickname", "avatar_url", "bio", "status"}
PRIVATE_KEYS = {
    "id",
    "nickname",
    "avatar_url",
    "bio",
    "email",
    "phone",
    "status",
    "created_at",
    "last_login_at",
}
TOKEN_PAIR_KEYS = {"access_token", "refresh_token", "token_type"}


def _register(client, account="alice", password="pass12345", **extra) -> dict:
    r = client.post(
        REGISTER_URL, json={"account": account, "password": password, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_token(
    *, token_type: str, expired: bool = False, user_id: str | None = None
) -> str:
    """手工签一个 token，用来构造"过期/伪造类型"这类边界。"""
    s = get_settings()
    now = datetime.now(UTC)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)
    payload = {
        "sub": user_id or str(uuid4()),
        "type": token_type,
        "iat": now,
        "exp": exp,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, s.secret_key.get_secret_value(), algorithm=s.algorithm)


async def _disable(app, account: str) -> None:
    repo = app.state.auth_repo
    identity = await repo.get_identity(AuthProvider.PASSWORD, account)
    assert identity is not None
    user = await repo.get_user_by_id(identity.user_id)
    assert user is not None
    user.status = UserStatus.DISABLED
    await repo.update_user(user)


# ---------------------------------------------------------------- /users/me


def test_me_requires_token(client):
    r = client.get(ME_URL)
    assert r.status_code == 401
    assert r.json()["error_code"] == "AUTHENTICATION_FAILED"


def test_me_returns_private_profile(client, account):
    reg = _register(client, **account)
    r = client.get(ME_URL, headers=_auth(reg["access_token"]))

    assert r.status_code == 200
    body = r.json()
    assert set(body) == PRIVATE_KEYS
    assert body["id"] == reg["user"]["id"]


def test_me_rejects_refresh_token(client, account):
    """refresh token 不能当 access 用 —— 类型校验是防线。"""
    reg = _register(client, **account)
    r = client.get(ME_URL, headers=_auth(reg["refresh_token"]))

    assert r.status_code == 401
    assert r.json()["error_code"] == "AUTHENTICATION_FAILED"


def test_me_rejects_expired_token(client):
    r = client.get(
        ME_URL, headers=_auth(_make_token(token_type="access", expired=True))
    )
    assert r.status_code == 401


def test_me_rejects_token_of_disabled_user(client, account):
    reg = _register(client, **account)
    asyncio.run(_disable(client.app, account["account"]))

    r = client.get(ME_URL, headers=_auth(reg["access_token"]))

    assert r.status_code == 401


# ---------------------------------------------------------------- /users/{id}


def test_public_profile_is_anonymous(client, account):
    reg = _register(client, **account)
    r = client.get(f"/auth/users/{reg['user']['id']}")

    assert r.status_code == 200
    body = r.json()
    assert set(body) == PUBLIC_KEYS
    # 边界：公开响应绝不能泄露联系方式
    assert "email" not in body
    assert "phone" not in body


def test_public_profile_unknown_id_returns_404(client):
    r = client.get(f"/auth/users/{uuid4()}")
    assert r.status_code == 404
    assert r.json()["error_code"] == "USER_NOT_FOUND"


def test_error_body_contract(client):
    """所有业务异常的响应体统一是 {error_code, message}。"""
    r = client.get(f"/auth/users/{uuid4()}")
    assert set(r.json()) == {"error_code", "message"}


# ---------------------------------------------------------------- /token/refresh


def test_refresh_returns_new_token_pair(client, account):
    reg = _register(client, **account)
    r = client.post(REFRESH_URL, json={"refresh_token": reg["refresh_token"]})

    assert r.status_code == 200
    body = r.json()
    assert set(body) == TOKEN_PAIR_KEYS
    assert body["token_type"] == "bearer"


def test_new_access_token_works_after_refresh(client, account):
    """刷新出来的 access token 必须真的能用，而不是只有形状。"""
    reg = _register(client, **account)
    fresh = client.post(
        REFRESH_URL, json={"refresh_token": reg["refresh_token"]}
    ).json()

    r = client.get(ME_URL, headers=_auth(fresh["access_token"]))
    assert r.status_code == 200


def test_refresh_rejects_access_token(client, account):
    """access token 不能当 refresh 用 —— 否则等于永久续期。"""
    reg = _register(client, **account)
    r = client.post(REFRESH_URL, json={"refresh_token": reg["access_token"]})

    assert r.status_code == 401
    assert r.json()["error_code"] == "AUTHENTICATION_FAILED"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(_make_token(token_type="refresh", expired=True), id="expired"),
        pytest.param(_make_token(token_type="access"), id="wrong-type"),
    ],
)
def test_refresh_rejects_bad_tokens(client, token):
    r = client.post(REFRESH_URL, json={"refresh_token": token})
    assert r.status_code == 401


def test_refresh_rejects_disabled_user(client, account):
    reg = _register(client, **account)
    asyncio.run(_disable(client.app, account["account"]))

    r = client.post(REFRESH_URL, json={"refresh_token": reg["refresh_token"]})
    assert r.status_code == 401


# ---------------------------------------------------------------- token 内容异常


def _token_without_sub() -> str:
    s = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": uuid4().hex,
        },
        s.secret_key.get_secret_value(),
        algorithm=s.algorithm,
    )


def test_me_rejects_token_without_sub(client):
    r = client.get(ME_URL, headers=_auth(_token_without_sub()))
    assert r.status_code == 401


def test_me_rejects_token_with_non_uuid_sub(client):
    """sub 被篡改成非法 UUID 时，不能 500，要按凭证无效处理。"""
    r = client.get(
        ME_URL, headers=_auth(_make_token(token_type="access", user_id="not-a-uuid"))
    )
    assert r.status_code == 401


def test_me_rejects_token_sub_of_unknown_user(client):
    r = client.get(ME_URL, headers=_auth(_make_token(token_type="access")))
    assert r.status_code == 401


def test_duplicate_register_returns_409(client, account):
    """service 层要把仓库的 ConflictError 翻成 IDENTITY_TAKEN。"""
    _register(client, **account)
    r = client.post(REGISTER_URL, json=account)

    assert r.status_code == 409
    assert r.json()["error_code"] == "IDENTITY_TAKEN"
