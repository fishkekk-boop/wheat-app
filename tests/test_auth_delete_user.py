# tests/test_auth_delete_user.py
"""删除用户（软删除）的测试。

规则：只有 ADMIN 能删；删的是 `status=DELETED`，不是物理删除。
"""


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


def test_admin_soft_deletes_user(client, db, account):
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    db.set_role(account["account"], "admin")

    r = client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    assert r.status_code == 204
    row = db.get_user_status("bob")
    assert row.status == "deleted"          # 软删除，不是物理删除
    assert db.count_identities("bob") == 1  # 登录方式还在（数据可追溯）


def test_deleted_user_cannot_access(client, db, account):
    """被软删的用户，旧 token 立刻失效（require_active_user 拦截）。"""
    admin = _register(client, **account)
    victim = _register(client, account="bob", password="pass12345")
    db.set_role(account["account"], "admin")
    client.delete(
        f"/auth/users/{victim['user']['id']}", headers=_auth(admin["access_token"])
    )

    r = client.get(ME_URL, headers=_auth(victim["access_token"]))

    assert r.status_code == 401


def test_delete_unknown_user_returns_404(client, db, account):
    from uuid import uuid4

    admin = _register(client, **account)
    db.set_role(account["account"], "admin")

    r = client.delete(
        f"/auth/users/{uuid4()}", headers=_auth(admin["access_token"])
    )

    assert r.status_code == 404
    assert r.json()["error_code"] == "USER_NOT_FOUND"


def test_admin_cannot_delete_self(client, db, account):
    """管理员也不能删自己（防止把自己锁在门外）。"""
    admin = _register(client, **account)
    db.set_role(account["account"], "admin")

    r = client.delete(
        f"/auth/users/{admin['user']['id']}", headers=_auth(admin["access_token"])
    )

    assert r.status_code == 403
    assert r.json()["error_code"] == "FORBIDDEN"
