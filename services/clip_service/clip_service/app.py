"""CLIP 服务的 HTTP 接口。不依赖 torch：编码器从外面传进来，测试时可以换成假的。

    GET  /health         模型已加载即返回 200 和模型信息（后端的 /health 只看这里是否 200）
    POST /encode/text    {"texts": ["…"]} → 每条文本一个向量
    POST /encode/image   请求体就是一张图片的字节（PNG 或 JPEG）→ 一个向量

每个响应都带 model_name、model_version、dim（GLOBAL §4.3）。
错误响应的格式与后端一致：{"error": {"code": "...", "message": "..."}}。
超时由调用方负责（附录 A5）；本服务一次只算一个请求，其余排队。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from clip_service.config import ClipSettings
from clip_service.core import (
    EncodeError,
    Encoder,
    ImageTooLargeError,
    InvalidImageError,
    InvalidTextError,
)

logger = logging.getLogger("clip_service.app")


class HealthResponse(BaseModel):
    status: str
    model_name: str
    model_version: str
    dim: int
    device: str


class EncodeTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: list[str]


class EncodeTextResponse(BaseModel):
    model_name: str
    model_version: str
    dim: int
    vectors: list[list[float]]


class EncodeImageResponse(BaseModel):
    model_name: str
    model_version: str
    dim: int
    vector: list[float]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def create_app(encoder: Encoder, settings: ClipSettings) -> FastAPI:
    app = FastAPI(title="docmgr CLIP 模型服务", version="0.1.0")

    @app.exception_handler(EncodeError)
    async def _encode_error(_request: Request, exc: EncodeError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # 只报出错的位置和原因，不回显输入内容
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return _error(422, "VALIDATION_ERROR", f"请求格式不正确：{details}")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # 推理时内存不足等。日志里只记异常，不记输入内容
        logger.error("编码请求出错：%s", type(exc).__name__, exc_info=exc)
        return _error(500, "ENCODE_FAILED", f"编码失败（{type(exc).__name__}）")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        info = encoder.info
        return HealthResponse(
            status="ok",
            model_name=info.model_name,
            model_version=info.model_version,
            dim=info.dim,
            device=info.device,
        )

    # 用普通 def：推理是阻塞调用，FastAPI 会放到线程池里执行，不阻塞事件循环
    @app.post("/encode/text", response_model=EncodeTextResponse)
    def encode_text(body: EncodeTextRequest) -> EncodeTextResponse:
        if not body.texts:
            raise InvalidTextError("texts 不能为空")
        if len(body.texts) > settings.clip_max_texts:
            raise InvalidTextError(f"一次最多编码 {settings.clip_max_texts} 条文本")
        for index, text in enumerate(body.texts):
            if not text.strip():
                raise InvalidTextError(f"texts[{index}] 是空文本")
            if len(text) > settings.clip_max_text_chars:
                raise InvalidTextError(f"texts[{index}] 超过 {settings.clip_max_text_chars} 个字符")
        vectors = encoder.encode_texts(body.texts)
        info = encoder.info
        return EncodeTextResponse(
            model_name=info.model_name,
            model_version=info.model_version,
            dim=info.dim,
            vectors=vectors,
        )

    @app.post("/encode/image", response_model=EncodeImageResponse)
    async def encode_image(request: Request) -> EncodeImageResponse:
        limit = settings.clip_max_image_bytes
        # 超限时不存内容，但把请求体读完再回 413：提前断开的话，还在发送的调用方
        # 看到的是连接中断（Broken pipe），而不是这条错误信息。
        # Content-Length 可以不带或写错，所以不看它，边读边数
        chunks: list[bytes] = []
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received <= limit:
                chunks.append(chunk)
            else:
                chunks.clear()
        if received > limit:
            raise ImageTooLargeError(f"图片超过大小上限 {limit} 字节")
        data = b"".join(chunks)
        if not data:
            raise InvalidImageError("请求体为空：请把图片的字节作为请求体发送")
        vector = await run_in_threadpool(encoder.encode_image, data)
        info = encoder.info
        return EncodeImageResponse(
            model_name=info.model_name,
            model_version=info.model_version,
            dim=info.dim,
            vector=vector,
        )

    return app
