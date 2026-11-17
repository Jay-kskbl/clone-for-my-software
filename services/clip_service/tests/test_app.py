"""接口层的测试：编码器是假的，只验证路由、输入限制、错误响应的格式。"""

import pytest
from fastapi.testclient import TestClient

from clip_service.app import create_app
from clip_service.config import load_settings
from clip_service.core import ImageTooLargeError, InvalidImageError, ModelInfo

INFO = ModelInfo(
    model_name="ViT-B-16", model_version="cn_clip-1.6.0-abcdef012345", dim=3, device="cpu"
)


class FakeEncoder:
    """按输入内容给出固定向量；b"corrupt" 当作损坏图片，b"huge" 当作像素超限。"""

    def __init__(self) -> None:
        self.info = INFO
        self.text_calls: list[list[str]] = []
        self.image_calls: list[bytes] = []
        self.fail_with: Exception | None = None

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        if self.fail_with is not None:
            raise self.fail_with
        self.text_calls.append(texts)
        return [[float(len(t)), 0.0, 1.0] for t in texts]

    def encode_image(self, data: bytes) -> list[float]:
        self.image_calls.append(data)
        if data == b"corrupt":
            raise InvalidImageError("图片文件已损坏，无法解码")
        if data == b"huge":
            raise ImageTooLargeError("图片像素数超过上限 10")
        return [float(len(data)), 1.0, 0.0]


@pytest.fixture
def encoder() -> FakeEncoder:
    return FakeEncoder()


def _client(encoder: FakeEncoder, **environ: str) -> TestClient:
    settings = load_settings(env_file=None, environ=environ)
    return TestClient(create_app(encoder, settings), raise_server_exceptions=False)


@pytest.fixture
def client(encoder: FakeEncoder) -> TestClient:
    return _client(encoder)


def _assert_error(response, status: int, code: str) -> str:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]["message"]


# ---- /health ----


def test_health_reports_model_name_version_and_dim(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_name": "ViT-B-16",
        "model_version": "cn_clip-1.6.0-abcdef012345",
        "dim": 3,
        "device": "cpu",
    }


# ---- /encode/text ----


def test_encode_text_returns_one_vector_per_text_with_model_info(client, encoder):
    response = client.post("/encode/text", json={"texts": ["会议室的白板", "猫"]})
    assert response.status_code == 200
    assert response.json() == {
        "model_name": "ViT-B-16",
        "model_version": "cn_clip-1.6.0-abcdef012345",
        "dim": 3,
        "vectors": [[6.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
    }
    assert encoder.text_calls == [["会议室的白板", "猫"]]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"texts": "不是列表"},
        {"texts": [1, 2]},
        {"texts": ["a"], "extra": 1},
        {"texts": []},
        {"texts": ["ok", "   "]},
    ],
)
def test_encode_text_rejects_malformed_requests(client, encoder, payload):
    _assert_error(client.post("/encode/text", json=payload), 422, "VALIDATION_ERROR")
    assert encoder.text_calls == []


def test_encode_text_rejects_non_json_body(client):
    response = client.post(
        "/encode/text", content=b"not json", headers={"content-type": "application/json"}
    )
    _assert_error(response, 422, "VALIDATION_ERROR")


def test_encode_text_enforces_count_and_length_limits(encoder):
    client = _client(encoder, CLIP_MAX_TEXTS="2", CLIP_MAX_TEXT_CHARS="5")
    assert client.post("/encode/text", json={"texts": ["a", "b"]}).status_code == 200
    _assert_error(
        client.post("/encode/text", json={"texts": ["a", "b", "c"]}), 422, "VALIDATION_ERROR"
    )
    assert client.post("/encode/text", json={"texts": ["12345"]}).status_code == 200
    _assert_error(client.post("/encode/text", json={"texts": ["123456"]}), 422, "VALIDATION_ERROR")


def test_validation_message_does_not_echo_the_input(client):
    secret = "机密内容-不应出现在错误信息里"
    message = _assert_error(
        client.post("/encode/text", json={"texts": [secret], "extra": secret}),
        422,
        "VALIDATION_ERROR",
    )
    assert secret not in message


def test_unexpected_encoder_failure_is_a_500_not_an_empty_result(client, encoder):
    encoder.fail_with = RuntimeError("内部细节不应泄露")
    message = _assert_error(
        client.post("/encode/text", json={"texts": ["a"]}), 500, "ENCODE_FAILED"
    )
    assert "RuntimeError" in message
    assert "内部细节" not in message


# ---- /encode/image ----


def test_encode_image_takes_raw_bytes_and_returns_one_vector(client, encoder):
    response = client.post(
        "/encode/image", content=b"\x89PNG-fake", headers={"content-type": "image/png"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "model_name": "ViT-B-16",
        "model_version": "cn_clip-1.6.0-abcdef012345",
        "dim": 3,
        "vector": [9.0, 1.0, 0.0],
    }
    assert encoder.image_calls == [b"\x89PNG-fake"]


def test_encode_image_rejects_empty_body(client, encoder):
    _assert_error(client.post("/encode/image", content=b""), 422, "INVALID_IMAGE")
    assert encoder.image_calls == []


def test_corrupt_image_is_422(client):
    _assert_error(client.post("/encode/image", content=b"corrupt"), 422, "INVALID_IMAGE")


def test_too_many_pixels_is_413(client):
    _assert_error(client.post("/encode/image", content=b"huge"), 413, "IMAGE_TOO_LARGE")


def test_body_over_byte_limit_is_413_and_never_reaches_the_encoder(encoder):
    client = _client(encoder, CLIP_MAX_IMAGE_BYTES="10")
    assert client.post("/encode/image", content=b"x" * 10).status_code == 200
    _assert_error(client.post("/encode/image", content=b"x" * 11), 413, "IMAGE_TOO_LARGE")
    assert encoder.image_calls == [b"x" * 10]


def test_byte_limit_holds_without_content_length(encoder):
    """分块传输没有 Content-Length，只能靠边读边数。"""
    client = _client(encoder, CLIP_MAX_IMAGE_BYTES="10")

    def chunks():
        yield b"x" * 6
        yield b"x" * 6

    _assert_error(client.post("/encode/image", content=chunks()), 413, "IMAGE_TOO_LARGE")
    assert encoder.image_calls == []


# ---- 其他 ----


def test_unknown_path_and_wrong_method_use_the_error_envelope(client):
    _assert_error(client.get("/nope"), 404, "NOT_FOUND")
    _assert_error(client.get("/encode/text"), 405, "METHOD_NOT_ALLOWED")
