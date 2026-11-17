"""Chinese-CLIP 的封装：加载一次，编码文本和图片。只在 clip 环境里能导入。

预处理是固定的（GLOBAL §4.3，记录在 decisions.md D33）：
    图片：只接受 PNG、JPEG → 按 EXIF 方向摆正 → 转 RGB → cn_clip 自带的变换
          （双三次插值缩放到模型输入尺寸，不保持宽高比；按 CLIP 的均值、方差归一化）
    文本：cn_clip 的分词器，上下文长度 52 个 token，超出部分截断
    输出：L2 归一化后的 float32 向量
"""

import io
import logging
import threading
import warnings
from importlib import metadata
from pathlib import Path

import cn_clip.clip as clip
import torch
from cn_clip.clip.utils import _MODEL_INFO, create_model, image_transform
from PIL import Image, ImageOps, UnidentifiedImageError

from clip_service.config import ConfigError
from clip_service.core import (
    EncodeError,
    ImageTooLargeError,
    InvalidImageError,
    InvalidTextError,
    ModelInfo,
)
from clip_service.models import make_model_version

logger = logging.getLogger("clip_service.encoder")

ALLOWED_IMAGE_FORMATS = ("PNG", "JPEG")


def library_version() -> str:
    try:
        return metadata.version("cn_clip")
    except metadata.PackageNotFoundError:
        return ""


class ClipEncoder:
    def __init__(self, model, preprocess, info: ModelInfo, *, max_image_pixels: int) -> None:
        self._model = model
        self._preprocess = preprocess
        self._max_image_pixels = max_image_pixels
        self.info = info
        # 模型不保证能被多个线程同时调用，而且同时算多个请求只会互相抢 CPU：一次只算一个
        self._lock = threading.Lock()

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise InvalidTextError("texts 不能为空")
        tokens = clip.tokenize(texts).to(self.info.device)
        with self._lock, torch.inference_mode():
            features = self._model.encode_text(tokens)
        return _normalized_rows(features)

    def encode_image(self, data: bytes) -> list[float]:
        tensor = self._preprocess(self._decode(data)).unsqueeze(0).to(self.info.device)
        with self._lock, torch.inference_mode():
            features = self._model.encode_image(tensor)
        return _normalized_rows(features)[0]

    def _decode(self, data: bytes) -> Image.Image:
        """字节 → RGB 图片。先按文件头判断格式和像素数，再解码，避免像素炸弹占满内存。"""
        try:
            with warnings.catch_warnings():
                # 像素数由下面自己的上限判断；Pillow 的告警在这里升级为异常，统一按超限处理
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(data), formats=ALLOWED_IMAGE_FORMATS)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ImageTooLargeError(f"图片像素数超过上限 {self._max_image_pixels}") from exc
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            raise InvalidImageError("无法识别的图片：只支持 PNG 和 JPEG，或文件已损坏") from exc

        width, height = image.size
        if width <= 0 or height <= 0:
            raise InvalidImageError("图片尺寸不合法")
        if width * height > self._max_image_pixels:
            raise ImageTooLargeError(
                f"图片像素数 {width * height} 超过上限 {self._max_image_pixels}"
            )
        try:
            image.load()
            # 手机照片常靠 EXIF 记录方向；不摆正的话编码的是横躺的画面，与用户看到的不一致
            image = ImageOps.exif_transpose(image)
            return image.convert("RGB")
        except (OSError, ValueError, SyntaxError, EOFError, IndexError, MemoryError) as exc:
            # 截断、数据段损坏等只有解码时才暴露
            raise InvalidImageError("图片文件已损坏，无法解码") from exc


def _normalized_rows(features: "torch.Tensor") -> list[list[float]]:
    features = features.float()
    norms = features.norm(dim=-1, keepdim=True)
    if not bool(torch.isfinite(features).all()) or bool((norms == 0).any()):
        # 不把无效向量交给调用方：写进索引后会让相似度计算出错
        raise EncodeError("模型输出了无效的向量")
    return (features / norms).cpu().tolist()


def load_encoder(
    model_path: Path,
    *,
    model_name: str,
    device: str,
    sha256: str,
    max_image_pixels: int,
) -> ClipEncoder:
    """从本地权重文件加载模型。任何问题都抛 ConfigError（启动失败，退出码 1）。

    不使用 cn_clip.load_from_name：它在文件缺失时会自动下载（GLOBAL §3.4 禁止）。
    """
    if model_name not in _MODEL_INFO:
        raise ConfigError(
            "CLIP 服务无法启动：CLIP_MODEL_NAME 不是 cn_clip 支持的模型，"
            f"可选：{sorted(_MODEL_INFO)}"
        )
    if device == "mps" and not torch.backends.mps.is_available():
        raise ConfigError("CLIP 服务无法启动：CLIP_DEVICE=mps，但本机的 PyTorch 不支持 MPS")
    if device == "cuda" and not torch.cuda.is_available():
        raise ConfigError("CLIP 服务无法启动：CLIP_DEVICE=cuda，但本机没有可用的 CUDA")

    spec = _MODEL_INFO[model_name]
    try:
        with model_path.open("rb") as fh:
            # weights_only=True：只读张量，不执行权重文件里可能夹带的任意代码
            checkpoint = torch.load(fh, map_location="cpu", weights_only=True)
        model = create_model(spec["struct"], checkpoint)
        del checkpoint
        if device == "cpu":
            # create_model 把权重转成了半精度，CPU 上要转回单精度
            model.float()
        else:
            model.to(device)
        model.eval()
    except Exception as exc:  # noqa: BLE001 —— 权重与结构不匹配、文件损坏、内存不足都在这里
        logger.exception("加载模型失败")
        raise ConfigError(
            f"CLIP 服务无法启动：加载模型失败（{type(exc).__name__}）。"
            "请确认权重文件完整，且与 CLIP_MODEL_NAME 对应"
        ) from exc

    preprocess = image_transform(spec["input_resolution"])
    info = ModelInfo(
        model_name=model_name,
        model_version=make_model_version(library_version(), sha256),
        dim=0,
        device=device,
    )
    encoder = ClipEncoder(model, preprocess, info, max_image_pixels=max_image_pixels)
    try:
        # 启动时就算一次：确认模型真的能推理，并取得向量维度
        dim = len(encoder.encode_texts(["启动自检"])[0])
    except Exception as exc:  # noqa: BLE001
        logger.exception("模型自检失败")
        raise ConfigError(f"CLIP 服务无法启动：模型自检失败（{type(exc).__name__}）") from exc
    encoder.info = ModelInfo(
        model_name=info.model_name, model_version=info.model_version, dim=dim, device=device
    )
    return encoder
