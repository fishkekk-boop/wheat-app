"""Auth 服务异常"""

from wheat_app.core.exceptions import AlreadyExists


class IdentityAlreadyTaken(AlreadyExists):
    error_code = "IDENTITY_TAKEN"
    default_message = "改身份已被占用"
