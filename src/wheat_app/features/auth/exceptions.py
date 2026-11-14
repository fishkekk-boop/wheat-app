"""Auth 模块的业务异常。

放在 feature 内而不是 core：这些是"注册/登录"特有的语义，
其他 feature 不该认识 ``IdentityAlreadyTaken`` 这种词。
"""

from wheat_app.core.exceptions import AlreadyExists, AuthenticationError, NotFound


class IdentityAlreadyTaken(AlreadyExists):
    """该登录标识已被占用（409）。

    **何时用**：注册时用户名/手机号/邮箱已被别的账号绑定。
    **由谁抛**：``AuthService._create_account``（把仓库的 ``ConflictError`` 翻译过来）。
    **为什么不让 ``ConflictError`` 直接冒到 API 层**：那个异常带
    ``entity/identifier``，是存储细节；对外只需要"这个账号被占了"这个业务事实。
    """

    error_code = "IDENTITY_TAKEN"
    default_message = "该身份已被占用"


class UserNotFound(NotFound):
    """用户不存在（404）。

    **何时用**：按 id 查用户资料却查不到（``/auth/users/{id}``）。
    **注意**：登录场景**不要**用它——登录失败必须统一返回
    ``InvalidCredentials``，否则会暴露"账号是否存在"。
    """

    error_code = "USER_NOT_FOUND"
    default_message = "用户不存在"


class UserDisabled(AuthenticationError):
    error_code = "AUTHENTICATION_FAILED"
    default_message = "用户已禁用"
