"""/health：依赖不可用时如实报告，而不是报错退出。"""

import socket

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.config import Settings
from app.main import create_app


def _closed_port() -> int:
    """取一个当前没有进程监听的本地端口。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def settings(tmp_path) -> Settings:
    port = _closed_port()
    return Settings(
        _env_file=None,
        database_url=f"postgresql://u:secret-pw@127.0.0.1:{port}/db",
        opensearch_url=f"http://127.0.0.1:{port}",
        clip_service_url=f"http://127.0.0.1:{port}",
        jwt_secret="unit-test-secret-not-used-anywhere-else-0123456789",
        storage_root=tmp_path / "storage",
        health_check_timeout_seconds=1,
    )


def test_all_dependencies_down_still_returns_200(settings):
    client = TestClient(create_app(settings))

    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    for component in ("database", "opensearch", "clip_service"):
        assert body[component]["status"] == "unavailable"
        assert body[component]["detail"]
    assert "secret-pw" not in resp.text


def _fake_get(responses: dict[str, httpx.Response]):
    def fake(url, **kwargs):
        for suffix, response in responses.items():
            if url.endswith(suffix):
                response.request = httpx.Request("GET", url)
                return response
        raise httpx.ConnectError("connection refused")

    return fake


def test_components_reported_independently(settings, monkeypatch):
    # OpenSearch 正常、CLIP 挂掉、数据库挂掉：三项互不影响
    monkeypatch.setattr(
        health.httpx,
        "get",
        _fake_get({"/_cluster/health": httpx.Response(200, json={"status": "yellow"})}),
    )
    client = TestClient(create_app(settings))

    body = client.get("/health").json()

    assert body["status"] == "degraded"
    assert body["opensearch"]["status"] == "ok"
    assert body["clip_service"]["status"] == "unavailable"
    assert body["database"]["status"] == "unavailable"


def test_all_ok(settings, monkeypatch):
    monkeypatch.setattr(
        health.httpx,
        "get",
        _fake_get(
            {
                "/_cluster/health": httpx.Response(200, json={"status": "green"}),
                "/health": httpx.Response(200, json={"status": "ok"}),
            }
        ),
    )
    monkeypatch.setattr(health, "check_database", lambda s: health.ComponentStatus(status="ok"))
    client = TestClient(create_app(settings))

    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert {body[c]["status"] for c in ("database", "opensearch", "clip_service")} == {"ok"}


def test_red_cluster_and_http_error_count_as_unavailable(settings, monkeypatch):
    monkeypatch.setattr(
        health.httpx,
        "get",
        _fake_get(
            {
                "/_cluster/health": httpx.Response(200, json={"status": "red"}),
                "/health": httpx.Response(503),
            }
        ),
    )

    assert health.check_opensearch(settings).status == "unavailable"
    assert health.check_clip_service(settings).status == "unavailable"


# T24b：/health 是公开接口，响应里不能带内部主机名、端口和数据库用户名


def test_unavailable_detail_has_no_host_port_or_user(settings, caplog):
    client = TestClient(create_app(settings))
    port = settings.database_url.rsplit(":", 1)[1].split("/")[0]

    with caplog.at_level("WARNING", logger="app.api.health"):
        resp = client.get("/health")

    body = resp.json()
    for component in ("database", "opensearch", "clip_service"):
        detail = body[component]["detail"]
        # 只有异常类型，例如 OperationalError、ConnectError
        assert detail.isidentifier(), detail
    for leaked in ("127.0.0.1", port, "secret-pw", "postgresql://", "u@"):
        assert leaked not in resp.text
    # 详细原因仍然写进服务端日志，便于排查；密码不进日志
    assert "健康检查：database 不可用：OperationalError" in caplog.text
    assert "健康检查：opensearch 不可用：ConnectError" in caplog.text
    assert "secret-pw" not in caplog.text


def test_http_error_detail_keeps_only_the_status_code(settings, monkeypatch):
    monkeypatch.setattr(
        health.httpx, "get", _fake_get({"/health": httpx.Response(503, text="internal-host:8001")})
    )

    status = health.check_clip_service(settings)

    assert status.status == "unavailable"
    assert status.detail == "HTTPStatusError: HTTP 503"


def test_database_auth_failure_detail_hides_the_user(settings, monkeypatch):
    def fail_auth(*_args, **_kwargs):
        raise psycopg.OperationalError(
            'connection to server at "db.internal" (10.0.0.5), port 5432 failed: '
            'FATAL:  password authentication failed for user "docmgr"'
        )

    monkeypatch.setattr(health.psycopg, "connect", fail_auth)

    status = health.check_database(settings)

    assert status.status == "unavailable"
    assert status.detail == "OperationalError"
