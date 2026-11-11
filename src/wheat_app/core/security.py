# src/wheat_app/core/security.py
"""密码哈希、JWT 签发/验证"""

from pwdlib import PasswordHash

# 创建密码哈希器实例：Arogn2id 算法
_password_hash = PasswordHash.recommended()

# 虚拟哈希，用户不存在时用虚拟值进行哈希比对，防御“时序攻击”
DUMMY_HASH = _password_hash.hash("dummypassword")


# 调用方是 async def 时，对verify_password / get_password_hash函数调用会阻塞事件循环
# 后续考虑包装为 async def 并在内部走线程池
def verify_password(plain_password, hashed_password) -> bool:
    """对密码和哈希后的值进行比对"""
    return _password_hash.verify(plain_password, hashed_password)


def hash_secret(password: str) -> str:
    """对密码进行哈希并返回结果"""
    return _password_hash.hash(password)
