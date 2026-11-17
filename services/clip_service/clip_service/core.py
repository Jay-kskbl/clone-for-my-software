"""模型信息、编码器接口和错误类型。

本模块不依赖 torch、cn_clip、PIL：接口层（app.py）和用假编码器的测试只依赖它，
所以能在没有装深度学习框架的环境里导入。
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelInfo:
    """写进每个响应、并由调用方存进 image_embeddings 的模型标识（GLOBAL §4.3）。"""

    model_name: str
    model_version: str
    dim: int
    device: str


class EncodeError(Exception):
    """编码请求无法完成。message 可以直接返回给调用方，不含输入内容。"""

    status_code = 500
    code = "ENCODE_FAILED"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ImageTooLargeError(EncodeError):
    status_code = 413
    code = "IMAGE_TOO_LARGE"


class InvalidImageError(EncodeError):
    status_code = 422
    code = "INVALID_IMAGE"


class InvalidTextError(EncodeError):
    status_code = 422
    code = "VALIDATION_ERROR"


class Encoder(Protocol):
    """app.py 需要的编码器接口。返回的向量都已做 L2 归一化。"""

    info: ModelInfo

    def encode_texts(self, texts: list[str]) -> list[list[float]]: ...

    def encode_image(self, data: bytes) -> list[float]: ...
