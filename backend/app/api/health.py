"""GET /health：分别报告数据库、OpenSearch、CLIP 服务的状态。

依赖不可用是需要如实报告的状态，不是让接口报错的理由（GLOBAL §12），
所以每项检查都自己接住异常，接口始终返回 200。

这是公开接口：不可用时 detail 只给异常类型，详细原因只写服务端日志（T24b）。
"""

import logging
from typing import Literal

import httpx
import psycopg
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter()


class ComponentStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    # degraded：至少一个依赖不可用
    status: Literal["ok", "degraded"]
    database: ComponentStatus
    opensearch: ComponentStatus
    clip_service: ComponentStatus


def _public_detail(exc: Exception) -> str:
    """响应里只放异常类型（HTTP 错误再加状态码）。

    /health 是公开接口，不登录也能访问。异常消息里会有内部主机名、端口和地址，
    数据库认证失败时还有数据库用户名，这些只写日志（T24b，D41）。
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{type(exc).__name__}: HTTP {exc.response.status_code}"
    return type(exc).__name__


def _unavailable(component: str, exc: Exception) -> ComponentStatus:
    # 日志里记完整的异常类型和消息，便于排查；连接串本身（可能带密码）从不写进日志和响应
    logger.warning("健康检查：%s 不可用：%s: %s", component, type(exc).__name__, exc)
    return ComponentStatus(status="unavailable", detail=_public_detail(exc))


def check_database(settings: Settings) -> ComponentStatus:
    try:
        # libpq 的 connect_timeout 是整数秒，且小于 2 会被当作 2
        timeout = max(2, round(settings.health_check_timeout_seconds))
        with psycopg.connect(settings.database_url, connect_timeout=timeout) as conn:
            conn.execute("SELECT 1")
        return ComponentStatus(status="ok")
    except Exception as exc:  # noqa: BLE001 —— 任何失败都要如实报告为不可用
        return _unavailable("database", exc)


def check_opensearch(settings: Settings) -> ComponentStatus:
    try:
        resp = httpx.get(
            f"{settings.opensearch_url.rstrip('/')}/_cluster/health",
            timeout=settings.health_check_timeout_seconds,
        )
        resp.raise_for_status()
        cluster_status = resp.json().get("status")
        # red 表示有主分片不可用，此时检索结果不可信
        if cluster_status == "red":
            return ComponentStatus(status="unavailable", detail="集群状态为 red")
        return ComponentStatus(status="ok", detail=f"集群状态为 {cluster_status}")
    except Exception as exc:  # noqa: BLE001
        return _unavailable("opensearch", exc)


def check_clip_service(settings: Settings) -> ComponentStatus:
    try:
        resp = httpx.get(
            f"{settings.clip_service_url.rstrip('/')}/health",
            timeout=settings.health_check_timeout_seconds,
        )
        resp.raise_for_status()
        return ComponentStatus(status="ok")
    except Exception as exc:  # noqa: BLE001
        return _unavailable("clip_service", exc)


# 用普通 def：三项检查都是阻塞调用，FastAPI 会放到线程池里执行，不阻塞事件循环
@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    database = check_database(settings)
    opensearch = check_opensearch(settings)
    clip_service = check_clip_service(settings)
    all_ok = all(c.status == "ok" for c in (database, opensearch, clip_service))
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        database=database,
        opensearch=opensearch,
        clip_service=clip_service,
    )
