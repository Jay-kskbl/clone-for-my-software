"""API 服务入口。

启动（在 backend/ 目录下）：
    uvicorn app.main:create_app --factory --reload

用工厂函数而不是模块级 app：配置检查发生在 create_app() 里，
缺配置时进程直接带着错误信息退出，而导入本模块本身不会失败（便于测试）。
"""

import sys

from fastapi import FastAPI

from app.api import health
from app.config import Settings, load_settings
from app.core.errors import ConfigError


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        try:
            settings = load_settings()
        except ConfigError as exc:
            # 只打印可读的说明，不打印一长串 traceback
            print(exc, file=sys.stderr)
            raise SystemExit(1) from exc

    app = FastAPI(title="智能文档管理系统 API")
    app.state.settings = settings
    app.include_router(health.router)
    return app
