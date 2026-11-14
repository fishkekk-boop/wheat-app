# src/wheat_app/core/security.py
"""密码哈希、JWT 签发/验证"""

import asyncio

from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

# 创建密码哈希器实例：Arogn2id 算法
_password_hash = PasswordHash.recommended()

# 虚拟哈希，用户不存在时用虚拟值进行哈希比对，防御“时序攻击”
DUMMY_HASH = _password_hash.hash("dummypassword")

# 读取请求头的依赖注入
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/password/form")


# 调用方是 async def 时，对verify_password / get_password_hash函数调用会阻塞事件循环
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """对密码和哈希后的值进行比对"""
    return _password_hash.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """对密码进行哈希并返回结果"""
    return _password_hash.hash(password)


# 包装同步函数至异步版本，将哈希计算卸载至线程池
async def hash_password_async(password: str) -> str:
    """argon2 是 CPU 密集操作，丢到线程池，避免阻塞事件循环。"""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """校验密码；同样走线程池。"""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)
