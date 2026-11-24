"""跨 feature 复用的 Pydantic 基类。"""

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """可从任意带属性的对象构造（不只是 ORM 对象）——即 ``from_attributes=True``。"""

    model_config = ConfigDict(from_attributes=True)
