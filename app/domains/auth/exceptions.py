"""auth 领域异常：继承全局 AppError 即可自动映射为 HTTP 状态码。"""
from app.core.exceptions import AppError


class InvalidCredentialsError(AppError):
    """用户名或密码错误（登录失败统一用这一个，防用户枚举）。"""

    status_code = 401
    detail = "用户名或密码错误"


class InvalidTokenError(AppError):
    """JWT 无效或过期。"""

    status_code = 401
    detail = "无效或过期的令牌"


class DuplicateUsernameError(AppError):
    """用户名已存在（409 Conflict）。"""

    status_code = 409
    detail = "用户名已存在"
