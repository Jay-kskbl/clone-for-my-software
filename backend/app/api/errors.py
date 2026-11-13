"""把异常转换成统一的错误响应：{"error": {"code": ..., "message": ...}}（docs/api.md §1.2）。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.core.errors import AppError

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return _error_response(exc.status_code, exc.code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # 只说哪个字段有什么问题，不回显提交的值：出错的字段可能就是密码
        problems = "；".join(
            f"{'.'.join(str(part) for part in err['loc'][1:]) or err['loc'][0]}：{err['msg']}"
            for err in exc.errors()
        )
        return _error_response(422, "VALIDATION_ERROR", f"请求参数不合法：{problems}")

    @app.exception_handler(OperationalError)
    def handle_database_down(_request: Request, exc: OperationalError) -> JSONResponse:
        # 连不上数据库、连接中断等。详情只写日志：异常信息里可能带主机名和库名
        logger.error("数据库不可用：%s", type(exc.orig).__name__)
        return _error_response(503, "DATABASE_UNAVAILABLE", "数据库不可用，请稍后重试")

    @app.exception_handler(Exception)
    def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("未预期的错误", exc_info=exc)
        return _error_response(500, "INTERNAL_ERROR", "服务器内部错误")
