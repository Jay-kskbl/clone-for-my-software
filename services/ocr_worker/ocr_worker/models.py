"""OCR 模型目录的检查，以及写进识别结果的模型名称和版本。

模型文件由人手动放到配置的目录里（GLOBAL §8.2）。目录缺失或不完整时启动直接报错退出，
不会自动下载。版本里带上模型权重文件的哈希（GLOBAL §3.4：实验配置中记录模型文件的 hash），
换了模型文件，版本就会变。
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ocr_worker.config import ConfigError

# PaddleOCR 3.x 导出的推理模型目录里必须有的文件
REQUIRED_FILES = ("inference.pdiparams", "inference.yml")
# 结构描述文件：新版是 inference.json，旧版是 inference.pdmodel，有一个即可
STRUCTURE_FILES = ("inference.json", "inference.pdmodel")
_WEIGHTS = "inference.pdiparams"
_HASH_CHARS = 8


@dataclass(frozen=True)
class ModelInfo:
    det_dir: Path
    rec_dir: Path
    det_sha256: str
    rec_sha256: str

    @property
    def det_name(self) -> str:
        return self.det_dir.name

    @property
    def rec_name(self) -> str:
        return self.rec_dir.name

    @property
    def model_name(self) -> str:
        """写进 ocr_results.model_name，例如 PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec。"""
        return f"{self.det_name}+{self.rec_name}"

    def model_version(self, library_version: str) -> str:
        """写进 ocr_results.model_version（≤64 个字符）：库版本 + 两个权重文件哈希的前 8 位。"""
        version = (
            f"paddleocr-{library_version}/"
            f"det-{self.det_sha256[:_HASH_CHARS]}/rec-{self.rec_sha256[:_HASH_CHARS]}"
        )
        return version[:64]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_dir(label: str, directory: Path) -> None:
    if not directory.is_dir():
        raise ConfigError(
            f"{label}模型目录不存在：{directory}\n"
            "  请把模型文件手动放到这个目录（或用环境变量指定其他目录）；本程序不会自动下载模型。"
        )
    missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]
    if not any((directory / name).is_file() for name in STRUCTURE_FILES):
        missing.append(" 或 ".join(STRUCTURE_FILES))
    if missing:
        raise ConfigError(f"{label}模型目录不完整：{directory}，缺少 {'、'.join(missing)}")


def check_models(det_dir: Path, rec_dir: Path) -> ModelInfo:
    """确认两个模型目录完整，并计算权重文件的哈希。有问题时抛 ConfigError。"""
    _check_dir("文本检测", det_dir)
    _check_dir("文字识别", rec_dir)
    return ModelInfo(
        det_dir=det_dir,
        rec_dir=rec_dir,
        det_sha256=_sha256(det_dir / _WEIGHTS),
        rec_sha256=_sha256(rec_dir / _WEIGHTS),
    )
