"""T21：CLIP 服务客户端。CLIP 服务用假的网络层代替。"""

import json

import httpx
import pytest

from app.modules.clip import ClipClient, ClipModel, ClipRejected, ClipUnavailable

MODEL_BODY = {"model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d", "dim": 3}
MODEL = ClipModel(model_name="ViT-B-16", model_version="cn_clip-1.6.0-5997ef32c50d", dim=3)


def client_for(handler) -> ClipClient:
    return ClipClient(
        "http://clip.test:8001/", timeout_seconds=1.0, transport=httpx.MockTransport(handler)
    )


def replying(status: int, body=None, *, raw: bytes | None = None):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body)

    return handler, seen


def test_model_reads_health():
    handler, seen = replying(200, {"status": "ok", "device": "cpu", **MODEL_BODY})
    assert client_for(handler).model() == MODEL
    assert (seen[0].method, seen[0].url.path) == ("GET", "/health")


def test_encode_image_posts_raw_bytes():
    handler, seen = replying(200, {**MODEL_BODY, "vector": [0.6, 0.8, 0]})
    encoded = client_for(handler).encode_image(b"\x89PNG-bytes")
    assert encoded.model == MODEL
    assert encoded.vector == [0.6, 0.8, 0.0]
    (request,) = seen
    assert (request.method, request.url.path) == ("POST", "/encode/image")
    assert request.content == b"\x89PNG-bytes"
    assert request.headers["content-type"] == "application/octet-stream"


@pytest.mark.parametrize(
    ("status", "code"), [(413, "IMAGE_TOO_LARGE"), (422, "INVALID_IMAGE"), (404, "NOT_FOUND")]
)
def test_rejections_are_not_retryable_and_carry_the_reason(status, code):
    handler, _ = replying(status, {"error": {"code": code, "message": "说明"}})
    with pytest.raises(ClipRejected) as excinfo:
        client_for(handler).encode_image(b"x")
    assert excinfo.value.retryable is False
    assert code in excinfo.value.message


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_server_errors_are_retryable(status):
    handler, _ = replying(status, {"error": {"code": "ENCODE_FAILED", "message": "x"}})
    with pytest.raises(ClipUnavailable) as excinfo:
        client_for(handler).encode_image(b"x")
    assert excinfo.value.retryable is True


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_connection_problems_are_retryable_and_hide_the_address(error):
    def handler(request):
        raise error("clip.test:8001 refused", request=request)

    with pytest.raises(ClipUnavailable) as excinfo:
        client_for(handler).model()
    assert "clip.test" not in excinfo.value.message
    assert excinfo.value.retryable is True


@pytest.mark.parametrize(
    "body",
    [
        {**MODEL_BODY, "vector": [0.1, 0.2]},  # 维度不对
        {**MODEL_BODY, "vector": [0.1, 0.2, "x"]},
        {**MODEL_BODY, "vector": [0.1, 0.2, True]},
        {**MODEL_BODY, "vector": [0.1, 0.2, None]},
        {**MODEL_BODY},  # 没有向量
        {**MODEL_BODY, "dim": 0, "vector": []},
        {**MODEL_BODY, "dim": "3", "vector": [1, 2, 3]},
        {**MODEL_BODY, "model_name": "", "vector": [1, 2, 3]},
        {**MODEL_BODY, "model_version": "v" * 65, "vector": [1, 2, 3]},
        {"vector": [1, 2, 3]},
        [1, 2, 3],
    ],
)
def test_malformed_responses_are_retryable_failures(body):
    handler, _ = replying(200, body)
    with pytest.raises(ClipUnavailable):
        client_for(handler).encode_image(b"x")


def test_non_json_success_is_a_failure():
    handler, _ = replying(200, raw=b"<html>proxy</html>")
    with pytest.raises(ClipUnavailable):
        client_for(handler).model()


def test_non_finite_vector_is_rejected():
    # JSON 里写不出 NaN，用 Python 的 json 扩展写法模拟一个不守规矩的服务
    handler, _ = replying(
        200, raw=b'{"model_name":"m","model_version":"v","dim":2,"vector":[NaN,1]}'
    )
    with pytest.raises(ClipUnavailable):
        client_for(handler).encode_image(b"x")


# ---- 查询文本编码（T22）----


def test_encode_text_posts_one_text_and_reads_its_vector():
    handler, seen = replying(200, {**MODEL_BODY, "vectors": [[0.6, 0, 0.8]]})
    encoded = client_for(handler).encode_text("会议室白板")
    assert encoded.model == MODEL
    assert encoded.vector == [0.6, 0.0, 0.8]
    (request,) = seen
    assert (request.method, request.url.path) == ("POST", "/encode/text")
    assert json.loads(request.content) == {"texts": ["会议室白板"]}


@pytest.mark.parametrize(
    "vectors",
    [None, [], [[1, 0, 0], [0, 1, 0]], [[1, 0]], [["a", 0, 0]], "x"],
    ids=["缺少", "空", "多于一条", "维度不对", "不是数字", "不是列表"],
)
def test_encode_text_rejects_malformed_vectors(vectors):
    handler, _ = replying(200, {**MODEL_BODY, "vectors": vectors})
    with pytest.raises(ClipUnavailable):
        client_for(handler).encode_text("q")


def test_encode_text_validation_error_is_a_rejection():
    handler, _ = replying(422, {"error": {"code": "VALIDATION_ERROR", "message": "x"}})
    with pytest.raises(ClipRejected):
        client_for(handler).encode_text("q")


def test_query_client_uses_the_search_timeout():
    from types import SimpleNamespace

    from app.modules.clip import query_clip_client_from_settings

    settings = SimpleNamespace(
        clip_service_url="http://clip.test:8001", search_image_timeout_seconds=2.5
    )
    with query_clip_client_from_settings(settings) as client:
        assert client._http.timeout.read == 2.5
