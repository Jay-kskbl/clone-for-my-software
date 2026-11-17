"""CLIP 服务的配置：项目根目录的 .env 加环境变量（环境变量优先），启动时一次性校验。

clip 环境里没有 pydantic-settings，所以这里自己读 .env（写法与 OCR Worker 相同）。
只读本服务用到的 CLIP_* 变量，其余一律忽略。本服务不连数据库，也不连 OpenSearch。
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# services/clip_service/clip_service/config.py → 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "clip" / "clip_cn_vit-b-16.pt"


class ConfigError(Exception):
    """配置或模型文件有问题，服务不能启动。信息可以直接打印给人看，不含任何变量的值。"""


class ClipSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    # ---- 模型（附录 A4；文件缺失时启动报错，不下载）----
    clip_model_path: Path = DEFAULT_MODEL_PATH
    # cn_clip 的模型结构名，必须与权重文件对应
    clip_model_name: str = Field(default="ViT-B-16", min_length=1, max_length=64)
    # 填了就在启动时核对权重文件的 sha256，不一致则不启动；不填只记录不核对
    clip_model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # 默认 cpu：不同机器上结果可复现（Barry 2026-11-17 选定，decisions.md D33）
    clip_device: Literal["cpu", "mps", "cuda"] = "cpu"

    # ---- 监听 ----
    # 默认只监听本机；接口没有鉴权，不要改成对外地址
    clip_host: str = Field(default="127.0.0.1", min_length=1)
    clip_port: int = Field(default=8001, ge=1, le=65535)

    # ---- 输入限制 ----
    # 一张图片的字节数上限；默认与上传上限（UPLOAD_MAX_BYTES）相同
    clip_max_image_bytes: int = Field(default=52_428_800, gt=0)
    # 一张图片的像素数上限（宽 × 高），解码前按文件头判断
    clip_max_image_pixels: int = Field(default=100_000_000, gt=0)
    # 一次请求最多编码多少条文本
    clip_max_texts: int = Field(default=32, gt=0, le=1024)
    # 单条文本的字符数上限（模型本身只用前 52 个 token，更长的部分被截断）
    clip_max_text_chars: int = Field(default=1000, gt=0)

    @field_validator("clip_model_sha256", mode="before")
    @classmethod
    def _lower_sha256(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("clip_model_path", mode="after")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        # 相对路径一律相对项目根目录，不随启动时的工作目录变化
        return value if value.is_absolute() else PROJECT_ROOT / value


def read_env_file(path: Path) -> dict[str, str]:
    """读一个 .env 文件：KEY=VALUE，忽略空行和 # 开头的注释，去掉值两边成对的引号。

    文件不存在时返回空字典（可以只用环境变量）。
    """
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_settings(
    env_file: Path | None = DEFAULT_ENV_FILE, environ: Mapping[str, str] | None = None
) -> ClipSettings:
    """读取并校验配置；有问题时抛 ConfigError，列出每个出错的变量名（不输出值）。

    env_file=None 表示只读环境变量（测试用）。
    """
    merged = read_env_file(env_file) if env_file is not None else {}
    merged.update(os.environ if environ is None else environ)
    # 变量名不区分大小写，统一按小写对应字段；空字符串视为没有设置（.env.example 里的空值）
    fields = set(ClipSettings.model_fields)
    data = {
        key.lower(): value for key, value in merged.items() if key.lower() in fields and value != ""
    }
    try:
        return ClipSettings(**data)
    except ValidationError as exc:
        invalid = [
            f"{str(err['loc'][0]).upper() if err['loc'] else '配置项'}（{err['msg']}）"
            for err in exc.errors()
        ]
        raise ConfigError(
            "CLIP 服务配置检查失败，无法启动：\n"
            f"  取值不合法：{'; '.join(invalid)}\n"
            "  请参照项目根目录的 .env.example 设置。"
        ) from exc
