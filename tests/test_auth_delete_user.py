# tests/test_auth_delete_user.py
"""删除用户（软删除）的测试。

规则：只有 ADMIN 能删；删的是 `status=DELETED`（不是物理删除），
且会把登录标识改名，使该账号名可以被重新注册。
"""

from uuid import uuid4

REGISTER_URL = "/auth/register/password"
ME_URL = "/auth/users/me"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client, account="alice", password="pass12345", **extra) -> dict:
    r = client.post(
        REGISTER_URL, json={"account": account, "password": password, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _make_admin(db, account: str) -> None:
    db.set_role(account, "admin")


# ---------------------------------------------------------------- 鉴权 / 权限


def test_delete_user_requires_token(client, account):
    reg = _register(client, **account)
    assert client.delete(f"/auth/users/{reg['user']['id']}").status_code == 401


def test_non_admin_cannot_delete(client, account):
    """普通用户删自己 → 403 FORBIDDEN。"""
    alice = _register(client, **account)

    r = client.delete(
        f"/auth/users/{alice['user']['id']}", headers=_auth(alice["access_token"])
    )

    assert r.status_code == 403
    assert r.json()["error_code"] == "FORBIDDEN"


def test_admin_cannot_delete_self(client, db, account):
    """管理员也不能删自己（防止把自己锁在门外）。"""
    admin = _register(client, **account)
    _make_admin(db, account["account"])

    r = client.delete(
        f"/auth/users/{admin['user']['id']}", headers=_auth(admin["access_token"])
    )

    assert r.status_code == 403
    assert r.json()["error_code"] == "FORBIDDEN"


def test_delete_unknown_user_returns_404(client, db, account):
    admin = _register(client, **account)
    _make_admin(db, account["account"])

    r = client.delete(f"/auth/users/{uuid4()}", headers=_auth(admin["access_token"]))

    assert r.status_code == 404
    assert r.json()["error_code"] == "USER_NOT_FOUND"


# ---------------------------------------------------------------- 软删除行为


def test_admin_soft_deletes_user(client, db, account):
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    _make_admin(db, account["account"])

    r = client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    assert r.status_code == 204
    row = db.get_user_status_by_id(victim["user"]["id"])
    assert row.status == "deleted"  # 软删除，不是物理删除
    # 登录身份仍保留（可追溯），只是被改名
    assert db.count_identities_by_user_id(victim["user"]["id"]) == 1


def test_soft_delete_renames_identifiers(client, db, account):
    """软删时必须把 identifier 改名，否则该标识会被唯一约束永久占用。"""
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    _make_admin(db, account["account"])
    client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    identifiers = db.get_identifiers(victim["user"]["id"])
    assert len(identifiers) == 1
    assert identifiers[0].startswith("bob_deleted_")


def test_deleted_account_name_can_register_again(client, db, account):
    """P1 回归：软删后同名账号必须能重新注册。"""
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    _make_admin(db, account["account"])
    client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    again = client.post(REGISTER_URL, json={"account": "bob", "password": "pass12345"})

    assert again.status_code == 201
    assert again.json()["user"]["nickname"] != victim["user"]["nickname"]


def test_deleted_user_cannot_access(client, db, account):
    """被软删的用户，旧 token 立刻失效（require_active_user 拦截）。"""
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    _make_admin(db, account["account"])
    client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    r = client.get(ME_URL, headers=_auth(victim["access_token"]))

    assert r.status_code == 401


def test_deleted_user_cannot_refresh_token(client, db, account):
    """被软删的用户也不能用 refresh token 续命。"""
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    _make_admin(db, account["account"])
    client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    r = client.post(
        "/auth/token/refresh", json={"refresh_token": victim["refresh_token"]}
    )

    assert r.status_code == 401


def test_deleted_user_public_profile_still_visible(client, db, account):
    """公开资料仍可按 id 查询（软删不回填 404），状态为 deleted。"""
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    _make_admin(db, account["account"])
    client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    r = client.get(f"/auth/users/{victim['user']['id']}")

    assert r.status_code == 200
    assert r.json()["status"] == "deleted"
