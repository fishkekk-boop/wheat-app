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
    IdentifierAlreadyBound,
    IdentityNotFound,
    LastIdentityRequired,
    ProviderAlreadyBound,
)
from wheat_app.features.auth.models import AuthProvider
from wheat_app.features.auth.repository_sql import SQLAlchemyAuthRepository
from wheat_app.features.auth.service import AuthService

REGISTER_URL = "/auth/register/password"
ME_URL = "/auth/users/me"
UPDATE_URL = "/auth/users/me"
PASSWORD = "pass12345"


def _register(client, account="alice", password="pass12345", **extra) -> dict:
    r = client.post(
        REGISTER_URL, json={"account": account, "password": password, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _unbind_url(provider: str) -> str:
    return f"/auth/users/me/identities/{provider}"


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
        assert len(await repo.get_identities_by_user_id(user.id)) == 2


async def test_bind_identifier_already_used_by_other_user(factory):
    """同一个邮箱被别的账号占了 → IdentifierAlreadyBound。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        alice = await _user_with_password(repo, "alice")
        await service.bind_identifier(
            user=alice, provider=AuthProvider.EMAIL, identifier="shared@example.com"
        )

        bob = await _user_with_password(repo, "bob")
        with pytest.raises(IdentifierAlreadyBound):
            await service.bind_identifier(
                user=bob, provider=AuthProvider.EMAIL, identifier="shared@example.com"
            )


async def test_bind_same_provider_twice_rejected(factory):
    """一个用户同一 provider 只能有一条身份。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)

        with pytest.raises(ProviderAlreadyBound):
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

        with pytest.raises(LastIdentityRequired):
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
    """解绑一个自己没绑定的 provider → IdentityNotFound。"""
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
    assert client.patch(UPDATE_URL, json={"nickname": "x"}).status_code == 401


def test_update_profile_updates_and_persists(client, account):
    reg = _register(client, **account)

    r = client.patch(
        UPDATE_URL,
        json={"nickname": "新昵称", "bio": "你好", "avatar_url": "https://a/b.png"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 200
    body = r.json()
    assert body["nickname"] == "新昵称"
    assert body["bio"] == "你好"
    assert body["avatar_url"] == "https://a/b.png"

    me = client.get(ME_URL, headers=_auth(reg["access_token"])).json()
    assert me["nickname"] == "新昵称"
    assert me["bio"] == "你好"


def test_update_profile_partial_keeps_other_fields(client, account):
    reg = _register(client, **account, nickname="原昵称")
    client.patch(
        UPDATE_URL, json={"bio": "只有简介"}, headers=_auth(reg["access_token"])
    )

    me = client.get(ME_URL, headers=_auth(reg["access_token"])).json()
    assert me["nickname"] == "原昵称"
    assert me["bio"] == "只有简介"


def test_update_profile_rejects_empty_nickname(client, account):
    reg = _register(client, **account)
    r = client.patch(
        UPDATE_URL, json={"nickname": ""}, headers=_auth(reg["access_token"])
    )
    assert r.status_code == 422


def test_update_profile_rejects_too_long_bio(client, account):
    reg = _register(client, **account)
    r = client.patch(
        UPDATE_URL, json={"bio": "x" * 501}, headers=_auth(reg["access_token"])
    )
    assert r.status_code == 422


def test_other_users_profile_untouched(client, account):
    """A 改资料不能影响 B。"""
    a = _register(client, **account)
    b = _register(client, account="bob", password="pass12345", nickname="Bob")

    client.patch(UPDATE_URL, json={"nickname": "Alice2"}, headers=_auth(a["access_token"]))

    me_b = client.get(ME_URL, headers=_auth(b["access_token"])).json()
    assert me_b["nickname"] == "Bob"


# ---------------------------------------------------------------- API：解绑


def test_unbind_identity_requires_token(client):
    r = client.request(
        "DELETE", _unbind_url("email"), json={"current_password": "pass12345"}
    )
    assert r.status_code == 401


def test_unbind_last_identity_returns_400(client, account):
    reg = _register(client, **account)
    r = client.request(
        "DELETE",
        _unbind_url("password"),
        json={"current_password": "pass12345"},
        headers=_auth(reg["access_token"]),
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "LAST_IDENTITY_REQUIRED"


def test_unbind_identity_removes_bound_provider(client, db, account):
    reg = _register(client, **account)
    db.add_identity(reg["user"]["id"], "email", "alice@example.com")
    assert db.count_identities(account["account"]) == 2

    r = client.request(
        "DELETE",
        _unbind_url("email"),
        json={"current_password": "pass12345"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 204
    assert db.count_identities(account["account"]) == 1


def test_unbind_identity_wrong_password_returns_401(client, db, account):
    reg = _register(client, **account)
    db.add_identity(reg["user"]["id"], "email", "alice@example.com")

    r = client.request(
        "DELETE",
        _unbind_url("email"),
        json={"current_password": "wrong-pass"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"
    assert db.count_identities(account["account"]) == 2


def test_unbind_unknown_provider_returns_404(client, db, account):
    reg = _register(client, **account)
    db.add_identity(reg["user"]["id"], "email", "alice@example.com")

    r = client.request(
        "DELETE",
        _unbind_url("phone"),
        json={"current_password": "pass12345"},
        headers=_auth(reg["access_token"]),
    )

    assert r.status_code == 404
    assert r.json()["error_code"] == "IDENTITY_NOT_FOUND"


# ---------------------------------------------------------------- API：登录方式列表


IDENTITIES_URL = "/auth/users/me/identities"


def test_list_identities_requires_token(client):
    assert client.get(IDENTITIES_URL).status_code == 401


def test_list_identities_returns_own_identities(client, db, account):
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
    _register(client, account="bob", password="pass12345")

    r = client.get(IDENTITIES_URL, headers=_auth(a["access_token"]))
    identifiers = {i["identifier"] for i in r.json()}

    assert identifiers == {account["account"]}
    assert "bob" not in identifiers


def test_register_defaults_to_role_user(client, account):
    assert _register(client, **account)["user"]["role"] == "user"


# ---------------------------------------------------------------- service：解绑不变量


@pytest.mark.xfail(
    reason="P2 修复不完整：只判断剩余身份「数量」，未判断剩余身份是否已验证/可登录",
    strict=False,
)
async def test_unbind_preserves_a_usable_identity(factory):
    """解绑后至少要留一条「已验证、可登录」的身份，否则用户会被锁死。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await _user_with_password(repo)
        # 绑一个未验证的 email 身份（当前没有验证流程，模拟绑定后未验证）
        await service.bind_identifier(
            user=user,
            provider=AuthProvider.EMAIL,
            identifier="alice@example.com",
            is_verified=False,
        )

        with pytest.raises(LastIdentityRequired):
            await service.unbind_identifier(
                user=user, provider=AuthProvider.PASSWORD, current_password=PASSWORD
            )


@pytest.mark.xfail(
    reason="P2 修复不完整：单条未验证身份也会被允许删除，导致零身份",
    strict=False,
)
async def test_unbind_only_unverified_identity_rejected(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        service = AuthService(repo)
        user = await repo.create_user_with_identity(
            provider=AuthProvider.PASSWORD,
            identifier="solo",
            nickname="Solo",
            secret_hash=hash_password(PASSWORD),
            is_verified=False,
        )

        with pytest.raises(LastIdentityRequired):
            await service.unbind_identifier(
                user=user, provider=AuthProvider.PASSWORD, current_password=PASSWORD
            )
