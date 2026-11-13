"""在读取请求体之前拒绝明显过大的上传。

FastAPI 在进入路由函数之前就会把整个 multipart 请求体收下来（大文件暂存到系统临时目录）。
只靠存储层的大小检查，一个 10 GB 的上传要等全部收完才被拒绝。这里先看 Content-Length：
超过上限就直接回 413，请求体一个字节都不读。

局限：不带 Content-Length 的分块上传不会在这里被拦住，它仍然会被收完，
然后由存储层在复制时按同一个上限拒绝（不会进入正式存储）。
"""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

# multipart 的分隔符、字段头、标签等不属于文件内容，留出余量，
# 避免一个恰好等于上限的文件被这里误拒；精确的上限由存储层执行。
_FORM_OVERHEAD_BYTES = 1024 * 1024


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, path: str, max_bytes: int) -> None:
        self._app = app
        self._path = path
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"] == self._path
            and self._declared_length(scope) > self._max_bytes + _FORM_OVERHEAD_BYTES
        ):
            await self._reject(send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    def _declared_length(scope: Scope) -> int:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return 0
        return 0

    async def _reject(self, send: Send) -> None:
        message = f"文件超过大小上限 {self._max_bytes / (1024 * 1024):g} MB"
        body = json.dumps(
            {"error": {"code": "FILE_TOO_LARGE", "message": message}}, ensure_ascii=False
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    # 请求体没有读，这条连接不能再复用
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
