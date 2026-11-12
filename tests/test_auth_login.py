# tests/test_auth_login.py
"""登录链路集成测试。

覆盖的是"行为"，不是"代码行"：走真实的 lifespan + 中间件 + 异常处理器 + 路由 + service + 仓库。
重点守三条线：
  1. 凭证校验（对/错/不存在/禁用）
  2. 防枚举（错误密码 与 账号不存在 的响应必须一模一样）
  3. 登录副作用（审计字段、token 内容）
"""

import asyncio
from datetime import UTC, datetime

import jwt
import pytest

from wheat_app.config import get_settings
from wheat_app.features.auth.models import AuthProvider, UserStatus

REGISTER_URL = "/auth/register/password"
LOGIN_URL = "/auth/login/password"
ACCESS_KEYS = {"access_token", "refresh_token", "token_type", "user"}
USER_KEYS = {
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


def _decode(token: str) -> dict:
    """用应用自己的密钥解码，顺便验证签名有效。"""
    s = get_settings()
    return jwt.decode(token, s.secret_key.get_secret_value(), algorithms=[s.algorithm])


def _register(client, account="alice", password="pass12345", **extra):
    r = client.post(
        REGISTER_URL, json={"account": account, "password": password, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, account="alice", password="pass12345"):
    return client.post(LOGIN_URL, json={"account": account, "password": password})


async def _set_status(app, account: str, status: UserStatus) -> None:
    repo = app.state.auth_repo
    identity = await repo.get_identity(AuthProvider.PASSWORD, account)
    assert identity is not None
    user = await repo.get_user_by_id(identity.user_id)
    assert user is not None
    user.status = status
    await repo.update_user(user)


# ---------------------------------------------------------------- 正常路径


def test_login_returns_token_pair(client, account):
    _register(client, **account)
    r = _login(client, **account)

    assert r.status_code == 200
    body = r.json()
    assert set(body) == ACCESS_KEYS
    assert body["token_type"] == "bearer"
    assert set(body["user"]) == USER_KEYS


def test_login_and_register_share_response_shape(client, account):
    """注册与登录复用同一个响应模型 —— 前端可以用同一套解析逻辑。"""
    registered = _register(client, **account)
    logged_in = _login(client, **account).json()

    assert set(registered) == set(logged_in) == ACCESS_KEYS
    assert set(registered["user"]) == set(logged_in["user"]) == USER_KEYS


def test_access_token_carries_user_id_and_type(client, account):
    registered = _register(client, **account)
    token = _login(client, **account).json()["access_token"]
    payload = _decode(token)

    assert payload["sub"] == registered["user"]["id"]
    assert payload["type"] == "access"
    assert payload["jti"]  # 每次签发唯一，未来做撤销用
    assert datetime.fromtimestamp(payload["exp"], UTC) > datetime.now(UTC)


def test_refresh_token_is_marked_as_refresh(client, account):
    """refresh 不能和 access 混用 —— type 字段是防线。"""
    _register(client, **account)
    body = _login(client, **account).json()

    assert _decode(body["access_token"])["type"] == "access"
    assert _decode(body["refresh_token"])["type"] == "refresh"


def test_two_logins_get_different_tokens(client, account):
    """每次登录签发新的 jti，避免 token 被重放识别不出来。"""
    _register(client, **account)
    first = _login(client, **account).json()
    second = _login(client, **account).json()

    assert first["access_token"] != second["access_token"]
    assert _decode(first["access_token"])["jti"] != _decode(second["access_token"])[
        "jti"
    ]


# ---------------------------------------------------------------- 失败路径


def test_login_wrong_password_returns_401(client, account):
    _register(client, **account)
    r = _login(client, account=account["account"], password="wrongpass1")

    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"


def test_unknown_account_and_wrong_password_are_indistinguishable(client, account):
    """防用户枚举：两种失败的响应体必须完全一致。"""
    _register(client, **account)

    wrong_password = _login(client, account=account["account"], password="wrongpass1")
    unknown_account = _login(client, account="nobody_here", password="wrongpass1")

    assert wrong_password.status_code == unknown_account.status_code == 401
    assert wrong_password.json() == unknown_account.json()


def test_disabled_user_cannot_login(client, account):
    _register(client, **account)
    asyncio.run(_set_status(client.app, account["account"], UserStatus.DISABLED))

    r = _login(client, **account)

    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"


@pytest.mark.parametrize(
    "payload",
    [
        {"account": "ab", "password": "pass12345"},  # account 太短
        {"account": "alice", "password": ""},  # 密码为空
        {"account": "alice!!", "password": "pass12345"},  # account 含非法字符
        {"account": "alice"},  # 缺密码
    ],
)
def test_login_payload_validation_returns_422(client, payload):
    r = client.post(LOGIN_URL, json=payload)
    assert r.status_code == 422


# ---------------------------------------------------------------- 登录副作用


def test_login_updates_audit_fields(client, account):
    registered = _register(client, **account)
    assert registered["user"]["last_login_at"] is None

    body = _login(client, **account).json()

    # 响应里就带着新的 last_login_at
    assert body["user"]["last_login_at"] is not None

    # 仓库里的 identity.last_used_at 也要更新
    async def _read():
        repo = client.app.state.auth_repo
        return await repo.get_identity(AuthProvider.PASSWORD, account["account"])

    identity = asyncio.run(_read())
    assert identity is not None
    assert identity.last_used_at is not None


def test_orphan_identity_still_returns_generic_401(client, account):
    """identity 还在、但 user 被删（数据不一致）时，也不能泄露"用户不存在"。"""
    _register(client, **account)

    # 直接清掉用户表，模拟"身份还在但用户没了"的脏数据
    client.app.state.auth_repo._users.clear()

    r = _login(client, **account)

    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"
    assert r.json()["message"] == "用户名或密码错误"
