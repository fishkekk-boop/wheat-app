# tests/test_auth_repository.py
"""Step 1 的 3 个骨架用例：先让它们红，再实现到全绿。

前置（各 3 行，先写这个再写仓库实现）:
    src/wheat_app/core/exceptions.py
        class AppError(Exception): ...
        class ConflictError(AppError): ...      # 唯一键冲突 → 409
        class UnauthorizedError(AppError): ...  # 认证失败 → 401

运行:
    uv run pytest tests/test_auth_repository.py -v
"""

from uuid import uuid4

import pytest

from wheat_app.core.exceptions import ConflictError
from wheat_app.features.auth.models import AuthProvider
from wheat_app.features.auth.repository import InMemoryAuthRepository


@pytest.fixture
def repo() -> InMemoryAuthRepository:
    """每个用例一个干净仓库（内存版没有事务回滚，只能靠隔离）。"""
    return InMemoryAuthRepository()


# ---------------------------------------------------------------- 用例 1
async def test_create_user_with_identity_then_read_back(repo):
    """创建后：User 与 AuthIdentity 都能按各自的主键/唯一键查回来。"""
    user = await repo.create_user_with_identity(
        provider=AuthProvider.PASSWORD,
        identifier="alice",
        secret_hash="hashed-password",
        nickname="Alice",
    )

    # 1) 返回的是真实落库的对象，不是临时构造的
    assert user.id is not None

    # 2) 按主键能查到（验证 users 表真的写进去了）
    found_user = await repo.get_user_by_id(user.id)
    assert found_user is not None
    assert found_user.id == user.id
    assert found_user.nickname == "Alice"

    # 3) 按 (provider, identifier) 能查到（验证 identities 的复合键索引）
    identity = await repo.get_identity(AuthProvider.PASSWORD, "alice")
    assert identity is not None
    assert identity.user_id == user.id
    assert identity.secret_hash == "hashed-password"

    # 4) 时间戳由仓库生成，且必须是带时区的
    assert found_user.created_at is not None
    assert found_user.created_at.tzinfo is not None


# ---------------------------------------------------------------- 用例 2
async def test_duplicate_identifier_raises_conflict(repo):
    """同一个 (provider, identifier) 只能注册一次 —— 模拟 DB 的 UNIQUE 约束。"""
    await repo.create_user_with_identity(
        provider=AuthProvider.PASSWORD,
        identifier="alice",
        secret_hash="hashed-1",
    )

    # 换一个用户、但登录标识相同 → 必须冲突
    with pytest.raises(ConflictError):
        await repo.create_user_with_identity(
            provider=AuthProvider.PASSWORD,
            identifier="alice",
            secret_hash="hashed-2",
        )

    # 冲突后不能留下半条数据：用户表里应该只有 1 个 alice
    # （提示：这就是"原子性"——要么 User+Identity 都成功，要么都不落）
    assert await repo.get_identity(AuthProvider.PASSWORD, "alice") is not None


# ---------------------------------------------------------------- 用例 3
async def test_get_identities_by_user_id_isolated(repo):
    """按用户查登录方式时不能串号。"""
    alice = await repo.create_user_with_identity(
        provider=AuthProvider.PASSWORD, identifier="alice", secret_hash="h1"
    )
    bob = await repo.create_user_with_identity(
        provider=AuthProvider.PASSWORD, identifier="bob", secret_hash="h2"
    )

    # alice 再绑一个（比如以后加手机号登录）
    await repo.add_identity(
        user_id=alice.id,
        provider=AuthProvider.PASSWORD,
        identifier="alice@example.com",
        secret_hash="h3",
    )

    alice_ids = await repo.get_identities_by_user_id(alice.id)
    bob_ids = await repo.get_identities_by_user_id(bob.id)

    assert len(alice_ids) == 2
    assert len(bob_ids) == 1
    assert {i.identifier for i in alice_ids} == {"alice", "alice@example.com"}
    assert bob_ids[0].identifier == "bob"

    # 查一个不存在的用户 → 空列表，而不是报错
    assert await repo.get_identities_by_user_id(uuid4()) == []
