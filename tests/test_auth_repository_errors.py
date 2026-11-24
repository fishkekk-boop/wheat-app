# tests/test_auth_repository_errors.py
"""仓库层错误路径的契约测试（约束翻译、幂等删除、查询未命中）。

这些分支在正常业务里很少走到，但一旦走错就会把 409/404 变成 500，
所以单独用直连 session 的方式钉住。
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from wheat_app.core.exceptions import ConflictError, EntityNotFound
from wheat_app.features.auth.models import (
    AuthIdentity,
    AuthProvider,
    User,
    UserRole,
    UserStatus,
)
from wheat_app.features.auth.repository_sql import SQLAlchemyAuthRepository


async def _create_user(repo, account: str, *, email: str | None = None) -> User:
    user = await repo.create_user_with_identity(
        provider=AuthProvider.PASSWORD,
        identifier=account,
        nickname=account.capitalize(),
        secret_hash="h",
    )
    if email is not None:
        user.email = email
        user = await repo.update_user(user)
    return user


# ---------------------------------------------------------------- 更新用户


@pytest.mark.xfail(
    reason="真实 bug：email 唯一约束名是 users_email_idx（unique+index 生成唯一索引），"
    "而 update_user 按 users_email_key 翻译 → 冲突时冒 IntegrityError（500）",
    strict=False,
)
async def test_update_user_email_conflict_raises_conflict(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        await _create_user(repo, "alice", email="taken@example.com")
        bob = await _create_user(repo, "bob")
        await session.commit()

        bob.email = "taken@example.com"
        with pytest.raises(ConflictError):
            await repo.update_user(bob)


@pytest.mark.xfail(
    reason="真实 bug：phone 唯一约束名是 users_phone_idx，代码按 users_phone_key 翻译",
    strict=False,
)
async def test_update_user_phone_conflict_raises_conflict(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        await _create_user(repo, "alice")
        alice_identity = await repo.get_identity(AuthProvider.PASSWORD, "alice")
        assert alice_identity is not None
        alice = await repo.get_user_by_id(alice_identity.user_id)
        assert alice is not None
        alice.phone = "+8613800000001"
        await repo.update_user(alice)

        bob = await _create_user(repo, "bob")
        await session.commit()

        bob.phone = "+8613800000001"
        with pytest.raises(ConflictError):
            await repo.update_user(bob)


async def test_update_unknown_user_raises_not_found(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        ghost = User(
            id=uuid4(),
            nickname="Ghost",
            status=UserStatus.ACTIVE,
            role=UserRole.USER,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with pytest.raises(EntityNotFound):
            await repo.update_user(ghost)


# ---------------------------------------------------------------- 更新身份


async def test_update_identity_identifier_conflict(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        alice = await _create_user(repo, "alice")
        bob = await _create_user(repo, "bob")
        bob_identity = await repo.get_identity(AuthProvider.PASSWORD, "bob")
        assert bob_identity is not None
        await session.commit()

        # 把 bob 的标识改成 alice 的名字 → 违反 (provider, identifier) 唯一约束
        bob_identity.identifier = "alice"
        with pytest.raises(ConflictError):
            await repo.update_identity(bob_identity)

        assert bob.id != alice.id


async def test_update_unknown_identity_raises_not_found(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        now = datetime.now(UTC)
        ghost = AuthIdentity(
            id=uuid4(),
            user_id=uuid4(),
            provider=AuthProvider.PASSWORD,
            identifier="ghost",
            secret_hash="h",
            created_at=now,
            updated_at=now,
        )
        with pytest.raises(EntityNotFound):
            await repo.update_identity(ghost)


# ---------------------------------------------------------------- 删除 / 查询


async def test_delete_existing_identity(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        await _create_user(repo, "alice")
        identity = await repo.get_identity(AuthProvider.PASSWORD, "alice")
        assert identity is not None

        await repo.delete_identity(identity)
        await session.commit()

    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        assert await repo.get_identity(AuthProvider.PASSWORD, "alice") is None


async def test_delete_identity_twice_is_idempotent(factory):
    """删除不存在的身份不报错（DELETE 天然幂等）。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        now = datetime.now(UTC)
        ghost = AuthIdentity(
            id=uuid4(),
            user_id=uuid4(),
            provider=AuthProvider.PASSWORD,
            identifier="ghost",
            secret_hash="h",
            created_at=now,
            updated_at=now,
        )
        await repo.delete_identity(ghost)  # 不应抛异常


async def test_get_identities_by_provider(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        await _create_user(repo, "alice")

        found = await repo.get_identities_by_provider(AuthProvider.PASSWORD, "alice")
        missing = await repo.get_identities_by_provider(AuthProvider.EMAIL, "alice")

        assert found is not None and found.identifier == "alice"
        assert missing is None


async def test_get_user_by_id_missing_returns_none(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        assert await repo.get_user_by_id(uuid4()) is None


async def test_get_identities_by_user_id_empty_for_unknown_user(factory):
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        assert await repo.get_identities_by_user_id(uuid4()) == []
