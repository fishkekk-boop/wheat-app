"""Auth 服务异常"""

from wheat_app.core.exceptions import AlreadyExists, NotFound


class IdentityAlreadyTaken(AlreadyExists):
    error_code = "IDENTITY_TAKEN"
    default_message = "该身份已被占用"


class UserNotFound(NotFound):
    error_code = "USER_NOT_FOUND"
    default_message = "无用户信息"
