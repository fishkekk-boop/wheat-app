# src/wheat_app/core/exceptions.py
"""基础异常类与全局异常处理器"""

from uuid import UUID


class AppError(Exception):
    """应用异常根节点"""

    error_code: str = "APP_ERROR"
    default_message: str = "应用错误"
    http_status: int = 500

    def __init__(self, message: str | None = None) -> None:
        self.message = message
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message or self.default_message,
        }


# ========== 业务异常：可预期，映射 4xx ==========


class DomainError(AppError):
    error_code = "DOMAIN_ERROR"
    default_message = "业务规则禁止此操作"
    http_status = 400


class InvalidCredentials(DomainError):
    error_code = "INVALID_CREDENTIALS"
    default_message = "无效凭据"
    http_status = 401


class NotFound(DomainError):
    error_code = "NOT_FOUND"
    default_message = "资源不存在"
    http_status = 404


class AlreadyExists(DomainError):
    error_code = "ALREADY_EXISTS"
    default_message = "资源已存在"
    http_status = 409


class ConflictError(AlreadyExists):
    """唯一约束冲突：entity = 冲突实体 identifier = 冲突唯一键"""

    def __init__(self, entity: str, identifier: str) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} 已存在：{identifier}")


class EntityNotFound(NotFound):
    def __init__(self, entity: str, entity_id: UUID | str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} 不存在: {entity_id}")


# ========== 基础设施异常：技术故障，映射 5xx ==========


class InfrastructureError(AppError):
    error_code = "INFRASTRUCTURE_ERROR"
    default_message = "服务暂不可用"
    http_status = 500

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message or self.default_message,
        }
