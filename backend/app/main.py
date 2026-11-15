"""API 服务入口。

启动（在 backend/ 目录下）：
    uvicorn app.main:create_app --factory --reload

用工厂函数而不是模块级 app：配置检查发生在 create_app() 里，
缺配置时进程直接带着错误信息退出，而导入本模块本身不会失败（便于测试）。
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, documents, health, tasks
from app.api import search as search_api
from app.api.errors import register_error_handlers
from app.api.upload_limit import UploadSizeLimitMiddleware
from app.config import Settings, load_settings
from app.core.errors import ConfigError
from app.db.session import make_engine, make_session_factory
from app.modules.storage import LocalStorage
from app.modules.text_index import client_from_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        try:
            settings = load_settings()
        except ConfigError as exc:
            # 只打印可读的说明，不打印一长串 traceback
            print(exc, file=sys.stderr)
            raise SystemExit(1) from exc

    # 创建引擎不会立刻连接数据库：数据库没启动时服务仍能起来，由 /health 如实报告
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        text_index.close()
        engine.dispose()

    # 创建客户端不会立刻连接 OpenSearch：它没启动时服务仍能起来，由 /health 如实报告
    text_index = client_from_settings(settings)

    app = FastAPI(title="智能文档管理系统 API", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    app.state.text_index = text_index
    # 启动时就创建存储目录：目录不可写的问题在启动时暴露，而不是等到第一次上传
    app.state.storage = LocalStorage(settings.storage_root)
    register_error_handlers(app)
    app.add_middleware(
        UploadSizeLimitMiddleware, path="/api/documents", max_bytes=settings.upload_max_bytes
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(tasks.router)
    app.include_router(search_api.router)
    return app
