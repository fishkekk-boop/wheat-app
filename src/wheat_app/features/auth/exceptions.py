"""Auth 模块的业务异常。

这里的异常都是"客户端需要据其改变行为"的业务事实；core 里的异常是
不含业务名词的语义骨架（404/409/401）。feature 异常只继承 core 的语义基类。
"""

from wheat_app.core.exceptions import (
    AlreadyExists,
    AuthenticationError,
    DomainError,
    NotFound,
)
from wheat_app.features.auth.models import AuthProvider


class IdentityAlreadyTaken(AlreadyExists):
    """注册时登录标识（用户名/邮箱/手机号）已被占用（409）。"""

    error_code = "IDENTITY_TAKEN"
    default_message = "该身份已被占用"


class IdentifierAlreadyBound(AlreadyExists):
    """绑定新登录方式时，该标识已被其他账号绑定（409）。"""

    error_code = "IDENTIFIER_TAKEN"
    default_message = "该标识已被其他账号绑定"


class ProviderAlreadyBound(AlreadyExists):
    """绑定新登录方式时，当前用户已经绑定过该 provider（409）。"""

    error_code = "PROVIDER_BOUND"
    default_message = "该登录方式已绑定"


class UserNotFound(NotFound):
    """按 id 查用户不存在（404）。

    注意：登录场景不要用它——登录失败必须统一返回 ``InvalidCredentials``，
    否则会暴露"账号是否存在"。
    """

    error_code = "USER_NOT_FOUND"
    default_message = "用户不存在"


class UserDisabled(AuthenticationError):
    """认证时用户处于不可用状态（禁用/删除）。

    对外 ``error_code`` 与 ``AuthenticationError`` 一致，不暴露"已禁用"这一
    事实（防枚举）；保留该类只是为了在日志里能区分失败原因。
    """

    default_message = "账号不可用"


class IdentityNotFound(NotFound):
    """解绑时用户并未绑定该 provider（404）。"""

    error_code = "IDENTITY_NOT_FOUND"

    def __init__(self, provider: AuthProvider) -> None:
        self.provider = provider
        super().__init__(f"未绑定 {provider.value} 登录方式")


class LastIdentityRequired(DomainError):
    """尝试解绑最后一种登录方式（400）。"""

    error_code = "LAST_IDENTITY_REQUIRED"
    default_message = "至少保留一种登录方式"
