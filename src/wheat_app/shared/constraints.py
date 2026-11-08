"""跨模块通用格式约束"""

# src/shared/constraints.py
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field, StringConstraints

# 需要去首尾空格的字符串。
StrippedStr = Annotated[str, StringConstraints(strip_whitespace=True)]


# E.164 手机号格式。
PhoneNumber = Annotated[str, Field(pattern=r"^\+?[1-9]\d{1,14}$")]


# 自动生成的主键 UUID。
UuidPk = Annotated[UUID, Field(default_factory=uuid4)]
