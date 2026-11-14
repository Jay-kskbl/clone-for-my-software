"""在把请求交给路由之前拒绝明显过大的上传。

FastAPI 在进入路由函数之前就会把整个 multipart 请求体收下来（大文件暂存到系统临时目录）。
只靠存储层的大小检查，一个 10 GB 的上传要全部写到临时目录之后才被拒绝。这里先看
Content-Length：超过上限就回 413，请求体不落盘、不进内存。

请求体仍然要读完再丢弃，不能不读就直接应答：客户端（包括开发代理和浏览器）此时还在发送
数据，服务端提前关闭连接，对方看到的是“连接被重置”，而不是 413 和它的说明。
读取并丢弃的量有上限（_MAX_DRAIN_BYTES），超过后直接断开，不无限陪着读。

局限：不带 Content-Length 的分块上传不会在这里被拦住，它仍然会被收完，
然后由存储层在复制时按同一个上限拒绝（不会进入正式存储）。
"""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

# multipart 的分隔符、字段头、标签等不属于文件内容，留出余量，
# 避免一个恰好等于上限的文件被这里误拒；精确的上限由存储层执行。
_FORM_OVERHEAD_BYTES = 1024 * 1024
# 为了让客户端收到 413，最多读取并丢弃这么多请求体；再大就直接断开连接
_MAX_DRAIN_BYTES = 256 * 1024 * 1024


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
            drained = await self._drain(receive)
            await self._reject(send, keep_alive=drained)
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

    @staticmethod
    async def _drain(receive: Receive) -> bool:
        """读取并丢弃请求体。返回 True 表示读完了；False 表示超过上限或客户端已断开。"""
        discarded = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return False  # http.disconnect
            discarded += len(message.get("body", b""))
            if not message.get("more_body", False):
                return True
            if discarded > _MAX_DRAIN_BYTES:
                return False

    async def _reject(self, send: Send, *, keep_alive: bool) -> None:
        message = f"文件超过大小上限 {self._max_bytes / (1024 * 1024):g} MB"
        body = json.dumps(
            {"error": {"code": "FILE_TOO_LARGE", "message": message}}, ensure_ascii=False
        ).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        if not keep_alive:
            # 请求体没有读完，这条连接上还有残留数据，不能再复用
            headers.append((b"connection", b"close"))
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send({"type": "http.response.body", "body": body})
