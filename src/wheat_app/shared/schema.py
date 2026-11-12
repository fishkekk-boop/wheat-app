from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """可从任意对象的属性构造的基类（不只是 ORM 对象）"""

    model_config = ConfigDict(from_attributes=True)
