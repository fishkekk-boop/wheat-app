# src/wheat_app/core/exceptions.py
"""全局异常体系。

设计原则
--------
1. **所有可预期错误终止于 ``AppError`` 子类**，由 ``register_exception_handlers``
   统一转成 ``{"error_code", "message"}`` 的 JSON 响应。
2. **按"责任层级"分家**：
   - ``DomainError``：业务规则不允许 → 4xx，**属于"用户做错了"**，不打堆栈。
   - ``InfrastructureError``：技术故障（DB 挂了、磁盘满）→ 5xx，**必须打堆栈**。
3. **越靠近数据层，越要转成"自己层的语义"**：repository 把
   ``IntegrityError`` 转成 ``ConflictError``，service 再把 ``ConflictError``
   转成 ``IdentityAlreadyTaken``；API 层只认识业务异常，不认识 SQL 异常。

新增异常时的三条自检
--------------------
- 它是"用户操作不当"（4xx）还是"系统坏了"（5xx）？
- ``error_code`` 是否唯一？（前端靠它做分支，**不要复用**）
- 消息会不会泄漏内部信息（SQL、表名、密钥、堆栈）？
"""

from uuid import UUID


class AppError(Exception):
    """所有业务/基础设施异常的根节点。

    **何时用**：永远不要直接抛它。只作为 ``except AppError`` 的兜底类型，
    以及给子类提供 ``error_code / default_message / http_status`` 的模板。

    **由谁抛**：仅子类。
    """

    error_code: str = "APP_ERROR"
    default_message: str = "应用错误"
    http_status: int = 500

    def __init__(self, message: str | None = None) -> None:
        self.message = message
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """转成响应体；``message`` 为空时回落到类的默认文案。"""
        return {
            "error_code": self.error_code,
            "message": self.message or self.default_message,
        }


# ========== 业务异常：可预期，映射 4xx（不打堆栈，最多 warning）==========


class DomainError(AppError):
    """业务规则异常基类（4xx）。

    **何时用**：请求合法、但违反业务规则（重复注册、状态不允许、资源不存在）。
    **由谁抛**：service 层为主；repository 只在"冲突"这类有明确业务含义时抛子类。

    ⚠️ 不要用它表示"参数格式错"——那是 Pydantic 校验的 422。
    """

    error_code = "DOMAIN_ERROR"
    default_message = "业务规则禁止此操作"
    http_status = 400


class InvalidCredentials(DomainError):
    """账号或密码错误（401）。

    **何时用**：登录失败——密码不匹配、账号不存在、身份缺少凭据。
    **安全要求**：以上三种情况必须抛**同一句话**，否则攻击者可枚举账号。
    **由谁抛**：``AuthService.login_with_password`` / ``_complete_login``。
    """

    error_code = "INVALID_CREDENTIALS"
    default_message = "用户名或密码错误"
    http_status = 401


class AuthenticationError(DomainError):
    """凭证无效：token 缺失、签名错误、类型不对、已过期、用户不可用（401）。

    **何时用**：请求已带凭证，但凭证不能证明"你是谁"。
    **与 ``InvalidCredentials`` 的区别**：那个是"登录时给错密码"，
    这个是"已登录但凭证失效"，前端处理不同（前者留在登录页，后者跳登录页）。
    **由谁抛**：``get_current_user``（依赖层）、``AuthService.refresh_token``、
    ``user_from_token_payload``。
    """

    error_code = "AUTHENTICATION_FAILED"
    default_message = "身份凭证无效或已过期"
    http_status = 401


class NotFound(DomainError):
    """资源不存在（404）。**何时用**：按 id 查不到，且这是"用户可见"的常规情况。"""

    error_code = "NOT_FOUND"
    default_message = "资源不存在"
    http_status = 404


class AlreadyExists(DomainError):
    """资源已存在（409）。**何时用**：创建时撞唯一键（用户名、邮箱、手机号）。"""

    error_code = "ALREADY_EXISTS"
    default_message = "资源已存在"
    http_status = 409


class ConflictError(AlreadyExists):
    """唯一约束冲突（409）——**数据层专用**。

    **何时用**：repository 写入前发现唯一键已存在（内存版手查，DB 版由 UNIQUE 约束
    + ``IntegrityError`` 触发）。
    **由谁抛**：repository。
    **谁来接**：service 应把它转成业务语义（如 ``IdentityAlreadyTaken``），
    避免上层看到 ``entity/identifier`` 这种存储细节。
    """

    def __init__(self, entity: str, identifier: str) -> None:
        self.entity = entity  # 冲突的实体名，如 "AuthIdentity"
        self.identifier = identifier  # 冲突的唯一键值，如 "password:alice"
        super().__init__(f"{entity} 已存在：{identifier}")


class EntityNotFound(NotFound):
    """按某个标识查实体失败（404），比 ``NotFound`` 多带上下文。

    **何时用**：想给出"哪个实体的哪个 id 不存在"时。
    **注意**：对外响应只暴露 ``message``，``entity_id`` 仅用于日志定位。
    """

    def __init__(self, entity: str, entity_id: UUID | str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} 不存在: {entity_id}")


# ========== 基础设施异常：技术故障，映射 5xx（必须打堆栈）==========


class InfrastructureError(AppError):
    """技术故障基类（5xx）。

    **何时用**：数据库连接失败、磁盘满、第三方 API 不可用——**不是用户的错**。
    **由谁抛**：repository / 外部客户端适配层。
    **处理约定**：``exception_handlers`` 会 ``logger.exception`` 打完整堆栈，
    但响应体只给通用文案，绝不外泄 SQL/连接串。
    """

    error_code = "INFRASTRUCTURE_ERROR"
    default_message = "服务暂不可用"
    http_status = 500
