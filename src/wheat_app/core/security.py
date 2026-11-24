# src/wheat_app/core/security.py
"""密码哈希与 JWT 令牌头的读取入口。"""

import asyncio

from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()  # argon2id

# 用户不存在时也用它做一次比对，避免通过响应时间枚举账号。
DUMMY_HASH = _password_hash.hash("dummypassword")

# OAuth2 的 Bearer token 解析依赖；tokenUrl 指向 form 登录端点，供 Swagger「Authorize」使用。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/password/form")


def hash_password(password: str) -> str:
    """返回密码的 argon2id 哈希。"""
    return _password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    return _password_hash.verify(plain_password, hashed_password)


async def hash_password_async(password: str) -> str:
    """``hash_password`` 的异步版本：argon2 是 CPU 密集操作，丢到线程池避免阻塞事件循环。"""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """``verify_password`` 的异步版本。"""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)
