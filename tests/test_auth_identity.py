# tests/test_auth_identity.py
"""登录方式绑定/解绑 + 资料更新的测试。

分两层：
- service 层（直连仓库）：验证业务规则（重复绑定、不能删最后一种登录方式）
- API 层：验证 HTTP 契约（鉴权、状态码、error_code、持久化）
"""

import pytest

from wheat_app.core.exceptions import EntityNotFound, InvalidCredentials
from wheat_app.core.security import hash_password
from wheat_app.features.auth.exceptions import (
    DeleteOnlyOne,
    IdentifierExists,
    IdentityNotFound,
    ProviderExists,
)
from wheat_app.features.auth.models import AuthProvider
from wheat_app.features.auth.repository_sql import SQLAlchemyAuthRepository
from wheat_app.features.auth.service import AuthService

REGISTER_URL = "/auth/register/password"
UPDATE_URL = "/auth/users/update/profile"
DELETE_IDENTIFIER_URL = "/auth/users/delete/identifier"
ME_URL = "/auth/users/me"


def _register(client, account="alice", password="pass12345", **extra) -> dict:
    r = client.post(
        REGISTER_URL, json={"account": account, "password": password, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


PASSWORD = "pass12345"


async def _user_with_password(repo, account="alice"):
    return await repo.create_user_with_identity(
        provider=AuthProvider.PASSWORD,
        identifier=account,
        nickname=account.capitalize(),
        secret_hash=hash_password(PASSWORD),
        is_verified=True,
    )


# ---------------------------------------------------------------- service：绑定


async def test_bind_email_adds_second_identity(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)

        identity = await service.bind_identifier(
            user=user, provider=AuthProvider.EMAIL, identifier="alice@example.com"
        )

        assert identity.provider is AuthProvider.EMAIL
        assert identity.user_id == user.id
        identities = await repo.get_identities_by_user_id(user.id)
        assert len(identities) == 2


async def test_bind_identifier_already_used_by_other_user(factory):
    """同一个邮箱被别的账号占了 → IdentifierExists。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        alice = await _user_with_password(repo, "alice")
        await service.bind_identifier(
            user=alice, provider=AuthProvider.EMAIL, identifier="shared@example.com"
        )

        bob = await _user_with_password(repo, "bob")
        with pytest.raises(IdentifierExists):
            await service.bind_identifier(
                user=bob, provider=AuthProvider.EMAIL, identifier="shared@example.com"
            )


async def test_bind_same_provider_twice_rejected(factory):
    """一个用户同一 provider 只能有一条身份。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)

        with pytest.raises(ProviderExists):
            await service.bind_identifier(
                user=user,
                provider=AuthProvider.PASSWORD,
                identifier="alice2",
                secret_hash="hashed",
            )


async def test_add_identity_to_unknown_user_raises_not_found(factory):
    from uuid import uuid4

    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        with pytest.raises(EntityNotFound):
            await repo.add_identity(
                user_id=uuid4(),
                provider=AuthProvider.EMAIL,
                identifier="ghost@example.com",
            )


# ---------------------------------------------------------------- service：解绑


async def test_unbind_last_identity_rejected(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)

        with pytest.raises(DeleteOnlyOne):
            await service.unbind_identifier(
                user=user, provider=AuthProvider.PASSWORD, current_password=PASSWORD
            )


async def test_unbind_removes_that_identity(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)
        await service.bind_identifier(
            user=user, provider=AuthProvider.EMAIL, identifier="alice@example.com"
        )

        await service.unbind_identifier(
            user=user, provider=AuthProvider.EMAIL, current_password=PASSWORD
        )

        remaining = await repo.get_identities_by_user_id(user.id)
        assert len(remaining) == 1
        assert remaining[0].provider is AuthProvider.PASSWORD


async def test_unbind_unknown_provider_returns_not_found(factory):
    """解绑一个自己没绑定的 provider → 404，而不是静默成功。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)
        await service.bind_identifier(
            user=user, provider=AuthProvider.EMAIL, identifier="alice@example.com"
        )

        with pytest.raises(IdentityNotFound):
            await service.unbind_identifier(
                user=user, provider=AuthProvider.PHONE, current_password=PASSWORD
            )


async def test_unbind_wrong_password_rejected(factory):
    """解绑是敏感操作：密码错 → InvalidCredentials，且身份还在。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)
        await service.bind_identifier(
            user=user, provider=AuthProvider.EMAIL, identifier="alice@example.com"
        )

        with pytest.raises(InvalidCredentials):
            await service.unbind_identifier(
                user=user, provider=AuthProvider.EMAIL, current_password="wrong-pass"
            )

        assert len(await repo.get_identities_by_user_id(user.id)) == 2


# ---------------------------------------------------------------- API：更新资料


def test_update_profile_requires_token(client):
    r = client.post(UPDATE_URL, json={"nickname": "x"})
    assert r.status_code == 401


def test_update_profile_updates_and_persists(client, account):
    reg = _register(client, **account)

    r = client.post(
        UPDATE_URL,
        json={"nickname": "新昵称", "bio": "你好", "avatar_url": "https://a/b.png"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 200
    body = r.json()
    assert body["nickname"] == "新昵称"
    assert body["bio"] == "你好"
    assert body["avatar_url"] == "https://a/b.png"

    # 持久化：重新查 /me
    me = client.get(ME_URL, headers=_auth(reg["access_token"])).json()
    assert me["nickname"] == "新昵称"
    assert me["bio"] == "你好"


def test_update_profile_partial_keeps_other_fields(client, account):
    reg = _register(client, **account, nickname="原昵称")
    client.post(
        UPDATE_URL,
        json={"bio": "只有简介"},
        headers=_auth(reg["access_token"]),
    )

    me = client.get(ME_URL, headers=_auth(reg["access_token"])).json()
    assert me["nickname"] == "原昵称"   # 没传就不动
    assert me["bio"] == "只有简介"


def test_update_profile_rejects_empty_nickname(client, account):
    reg = _register(client, **account)
    r = client.post(
        UPDATE_URL, json={"nickname": ""}, headers=_auth(reg["access_token"])
    )
    assert r.status_code == 422


def test_update_profile_rejects_too_long_bio(client, account):
    reg = _register(client, **account)
    r = client.post(
        UPDATE_URL, json={"bio": "x" * 501}, headers=_auth(reg["access_token"])
    )
    assert r.status_code == 422


def test_other_users_profile_untouched(client, account):
    """A 改资料不能影响 B。"""
    a = _register(client, **account)
    b = _register(client, account="bob", password="pass12345", nickname="Bob")

    client.post(
        UPDATE_URL, json={"nickname": "Alice2"}, headers=_auth(a["access_token"])
    )

    me_b = client.get(ME_URL, headers=_auth(b["access_token"])).json()
    assert me_b["nickname"] == "Bob"


# ---------------------------------------------------------------- API：解绑


def test_delete_identifier_requires_token(client):
    r = client.post(
        DELETE_IDENTIFIER_URL, json={"provider": "email", "password": "pass12345"}
    )
    assert r.status_code == 401


def test_delete_identifier_rejects_last_identity(client, account):
    reg = _register(client, **account)
    r = client.post(
        DELETE_IDENTIFIER_URL,
        json={"provider": "password", "password": "pass12345"},
        headers=_auth(reg["access_token"]),
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "DELETE_ONLY_ONE"


def test_delete_identifier_removes_bound_provider(client, db, account):
    reg = _register(client, **account)
    user_id = reg["user"]["id"]
    db.add_identity(user_id, "email", "alice@example.com")
    assert db.count_identities(account["account"]) == 2

    r = client.post(
        DELETE_IDENTIFIER_URL,
        json={"provider": "email", "password": "pass12345"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 200
    assert db.count_identities(account["account"]) == 1


# ---------------------------------------------------------------- API：JOIN 查询


IDENTITIES_URL = "/auth/users/me/identities"


def test_list_identities_requires_token(client):
    assert client.get(IDENTITIES_URL).status_code == 401


def test_list_identities_returns_own_identities(client, db, account):
    """users ⨝ auth_identities：返回当前用户的全部登录方式。"""
    reg = _register(client, **account)
    db.add_identity(reg["user"]["id"], "email", "alice@example.com")

    r = client.get(IDENTITIES_URL, headers=_auth(reg["access_token"]))

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert {i["provider"] for i in body} == {"password", "email"}
    assert all("identifier" in i and "is_verified" in i for i in body)


def test_list_identities_does_not_leak_other_users(client, account):
    a = _register(client, **account)
    b = _register(client, account="bob", password="pass12345")

    r = client.get(IDENTITIES_URL, headers=_auth(a["access_token"]))
    identifiers = {i["identifier"] for i in r.json()}

    assert identifiers == {account["account"]}       # 只有自己的
    assert "bob" not in identifiers


def test_register_defaults_to_role_user(client, account):
    reg = _register(client, **account)
    assert reg["user"]["role"] == "user"


def test_delete_identifier_wrong_password_returns_401(client, db, account):
    reg = _register(client, **account)
    db.add_identity(reg["user"]["id"], "email", "alice@example.com")

    r = client.post(
        DELETE_IDENTIFIER_URL,
        json={"provider": "email", "password": "wrong-pass"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"
    assert db.count_identities(account["account"]) == 2   # 身份还在


def test_delete_identifier_unknown_provider_returns_404(client, db, account):
    reg = _register(client, **account)
    db.add_identity(reg["user"]["id"], "email", "alice@example.com")

    r = client.post(
        DELETE_IDENTIFIER_URL,
        json={"provider": "phone", "password": "pass12345"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 404
    assert r.json()["error_code"] == "IDENTITY_NOT_FOUND"
