"""权重文件检查与模型版本字符串。不依赖 torch，可以单独测试。"""

import hashlib
from pathlib import Path

from clip_service.config import ConfigError

_HASH_BLOCK = 1024 * 1024


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(_HASH_BLOCK):
            digest.update(block)
    return digest.hexdigest()


def check_model_file(path: Path, expected_sha256: str | None = None) -> str:
    """确认权重文件存在（并在给了期望值时核对 sha256），返回文件的 sha256。

    文件缺失时报错而不是下载（GLOBAL §3.4、§8.2）。
    """
    if not path.is_file():
        raise ConfigError(
            f"CLIP 服务无法启动：找不到模型权重文件 {path}\n"
            "  请把权重文件手动放到该位置，或用 CLIP_MODEL_PATH 指定路径。本服务不会联网下载模型。"
        )
    try:
        actual = file_sha256(path)
    except OSError as exc:
        raise ConfigError(
            f"CLIP 服务无法启动：读不了模型权重文件 {path}（{type(exc).__name__}）"
        ) from exc
    if expected_sha256 is not None and actual != expected_sha256:
        raise ConfigError(
            f"CLIP 服务无法启动：模型权重文件 {path} 的 sha256 与 CLIP_MODEL_SHA256 不一致\n"
            f"  实际值：{actual}"
        )
    return actual


def make_model_version(library_version: str, sha256: str) -> str:
    """模型版本 = 推理库版本 + 权重文件哈希的前 12 位。

    权重文件或 cn_clip 版本任何一个变了，版本字符串就变，旧向量不会被当成新模型的向量
    （image_embeddings 按 sha256 + model_name + model_version 去重）。长度不超过 64。
    """
    return f"cn_clip-{library_version or 'unknown'}-{sha256[:12]}"[:64]
