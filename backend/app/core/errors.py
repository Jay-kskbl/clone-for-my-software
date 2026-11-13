"""项目内的错误类型。"""


class ConfigError(Exception):
    """配置缺失或不合法。启动时抛出，让进程带着可读的错误信息退出。"""


class AppError(Exception):
    """能直接转换成 HTTP 错误响应的业务错误（结构见 docs/api.md §1.2）。

    message 会原样返回给客户端：不得包含密码、令牌、服务器路径或文件内容。
    """

    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnauthenticatedError(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class UsernameTakenError(AppError):
    status_code = 409
    code = "USERNAME_TAKEN"


class TaskNotRetryableError(AppError):
    status_code = 409
    code = "TASK_NOT_RETRYABLE"


class FileTooLargeError(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "UNSUPPORTED_FILE_TYPE"


class RequestInvalidError(AppError):
    """请求内容不合法，但不是字段格式问题（那一类由 FastAPI 的参数校验直接返回 422）。"""

    status_code = 422
    code = "VALIDATION_ERROR"
