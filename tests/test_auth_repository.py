# tests/test_auth_repository.py
"""仓库层契约测试（打真实 Postgres 测试库）。

与之前内存版的关键差别：**事务是真的**。
- 每个用例自己开 session、自己 commit，才能验证"数据真的落库"
- 冲突用例必须跨事务：先提交 alice，再另起事务制造重复 → 才能验证"冲突时不留半条数据"
"""

from uuid import uuid4

import pytest

from wheat_app.core.exceptions import ConflictError, EntityNotFound
from wheat_app.features.auth.models import AuthProvider
from wheat_app.features.auth.repository_sql import SQLAlchemyAuthRepository


# ---------------------------------------------------------------- 用例 1
async def test_create_user_with_identity_then_read_back(factory):
    """创建后：User 与 AuthIdentity 都能按各自的主键/唯一键查回来。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        user = await repo.create_user_with_identity(
            provider=AuthProvider.PASSWORD,
            identifier="alice",
            secret_hash="hashed-password",
            nickname="Alice",
        )
        await session.commit()

    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)

        # 1) 按主键能查到（验证 users 表真的写进去了）
        found_user = await repo.get_user_by_id(user.id)
        assert found_user is not None
        assert found_user.id == user.id
        assert found_user.nickname == "Alice"

        # 2) 按 (provider, identifier) 能查到（验证唯一键真在库上）
        identity = await repo.get_identity(AuthProvider.PASSWORD, "alice")
        assert identity is not None
        assert identity.user_id == user.id
        assert identity.secret_hash == "hashed-password"

        # 3) 时间戳由数据库生成，且必须带时区
        assert found_user.created_at is not None
        assert found_user.created_at.tzinfo is not None


# ---------------------------------------------------------------- 用例 2
async def test_duplicate_identifier_raises_conflict(factory):
    """同一个 (provider, identifier) 只能注册一次 —— 由 DB 的 UNIQUE 约束保证。"""

    async def register(identifier: str, nickname: str) -> None:
        async with factory() as session:
            repo = SQLAlchemyAuthRepository(session)
            await repo.create_user_with_identity(
                provider=AuthProvider.PASSWORD,
                identifier=identifier,
                secret_hash="h",
                nickname=nickname,
            )
            await session.commit()

    await register("alice", "Alice")

    with pytest.raises(ConflictError):
        await register("alice", "Alice2")

    # 冲突后不能留下半条数据：alice 仍然只有一条
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        identity = await repo.get_identity(AuthProvider.PASSWORD, "alice")
        assert identity is not None
        # 冲突那次尝试没有留下第二条用户
        identities = await repo.get_identities_by_user_id(identity.user_id)
        assert len(identities) == 1


async def test_add_identity_with_unknown_user_raises_not_found(factory):
    """给不存在的用户绑登录方式 → 404，而不是"身份已存在"（409）。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        with pytest.raises(EntityNotFound):
            await repo.add_identity(
                user_id=uuid4(),
                provider=AuthProvider.PASSWORD,
                identifier="ghost",
                secret_hash="h",
            )


# ---------------------------------------------------------------- 用例 3
async def test_get_identities_by_user_id_isolated(factory):
    """按用户查登录方式时不能串号。"""
    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        alice = await repo.create_user_with_identity(
            provider=AuthProvider.PASSWORD,
            identifier="alice",
            secret_hash="h1",
            nickname="Alice",
        )
        bob = await repo.create_user_with_identity(
            provider=AuthProvider.PASSWORD,
            identifier="bob",
            secret_hash="h2",
            nickname="Bob",
        )
        # alice 再绑一个不同 provider（同一个 provider 只能有一条）
        await repo.add_identity(
            user_id=alice.id,
            provider=AuthProvider.EMAIL,
            identifier="alice@example.com",
        )
        await session.commit()

    async with factory() as session:
        repo = SQLAlchemyAuthRepository(session)
        alice_ids = await repo.get_identities_by_user_id(alice.id)
        bob_ids = await repo.get_identities_by_user_id(bob.id)

        assert len(alice_ids) == 2
        assert len(bob_ids) == 1
        assert {i.identifier for i in alice_ids} == {"alice", "alice@example.com"}
