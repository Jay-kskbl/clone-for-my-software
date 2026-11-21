"""OCR Worker 的配置：项目根目录的 .env 加环境变量（环境变量优先），启动时一次性校验。

ocr 环境里没有 pydantic-settings，所以这里自己读 .env。只读本 Worker 用到的变量，
其余（docker-compose、后端专用的）一律忽略。数据库、OpenSearch、存储目录与后端共用同一组变量。
"""

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# services/ocr_worker/ocr_worker/config.py → 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_MODEL_ROOT = PROJECT_ROOT / "models" / "ocr"


class ConfigError(Exception):
    """配置有问题，Worker 不能启动。信息可以直接打印给人看，不含任何变量的值。"""


class OcrSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    # ---- 必填（与后端共用）----
    database_url: str = Field(min_length=1)
    opensearch_url: str = Field(min_length=1)

    # ---- 可选（与后端共用）----
    opensearch_timeout_seconds: float = Field(default=10.0, gt=0)
    opensearch_index_prefix: str = Field(default="", pattern=r"^([a-z0-9][a-z0-9_-]*)?$")
    storage_root: Path = PROJECT_ROOT / "storage"

    # ---- 模型（附录 A4；路径缺失时启动报错，不下载）----
    ocr_det_model_dir: Path = DEFAULT_MODEL_ROOT / "PP-OCRv5_mobile_det"
    ocr_rec_model_dir: Path = DEFAULT_MODEL_ROOT / "PP-OCRv5_mobile_rec"
    ocr_device: str = Field(default="cpu", min_length=1)

    # ---- 识别参数（实验参数，随结果记录）----
    # PDF 页渲染成图片的分辨率
    ocr_pdf_dpi: int = Field(default=200, ge=72, le=600)
    # 置信度低于它的文字行不写进检索片段（识别结果照样全部保存）。默认 0：全部保留
    ocr_min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # 送去识别的图片的像素数上限（渲染后的 PDF 页同样受它限制）
    ocr_max_pixels: int = Field(default=100_000_000, gt=0)

    # ---- 运行（附录 A3）----
    ocr_worker_lease_seconds: float = Field(default=60.0, gt=0)
    ocr_worker_heartbeat_seconds: float = Field(default=15.0, gt=0)
    ocr_worker_poll_seconds: float = Field(default=2.0, gt=0)
    # 一页（或一张图片）的识别时间上限；超过就杀掉识别子进程
    ocr_worker_task_timeout_seconds: float = Field(default=300.0, gt=0)
    # 加载模型的时间上限（实测 mobile 约 11 秒）
    ocr_worker_load_timeout_seconds: float = Field(default=180.0, gt=0)
    # 识别子进程的内存上限（MB），只在 Linux 上有效（decisions.md D16）
    ocr_worker_memory_limit_mb: int = Field(default=3072, gt=0)
    ocr_worker_max_tasks: int = Field(default=200, gt=0)
    # 连接数据库最多等多久（秒，整数，最小有效值 2），与通用 Worker 的同名配置含义相同（T24k）
    ocr_worker_db_connect_timeout_seconds: int = Field(default=10, ge=2, le=300)

    @field_validator("storage_root", "ocr_det_model_dir", "ocr_rec_model_dir", mode="after")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        # 相对路径一律相对项目根目录，不随启动时的工作目录变化
        return value if value.is_absolute() else PROJECT_ROOT / value

    @model_validator(mode="after")
    def _heartbeat_shorter_than_lease(self) -> "OcrSettings":
        if self.ocr_worker_heartbeat_seconds * 2 > self.ocr_worker_lease_seconds:
            raise ValueError(
                "OCR_WORKER_HEARTBEAT_SECONDS 不能超过 OCR_WORKER_LEASE_SECONDS 的一半"
            )
        return self


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
) -> OcrSettings:
    """读取并校验配置；有问题时抛 ConfigError，列出每个出错的变量名（不输出值）。

    env_file=None 表示只读环境变量（测试用）。
    """
    merged = read_env_file(env_file) if env_file is not None else {}
    merged.update(os.environ if environ is None else environ)
    # 变量名不区分大小写，统一按小写对应字段；空字符串视为没有设置（.env.example 里的空值）
    fields = set(OcrSettings.model_fields)
    data = {
        key.lower(): value
        for key, value in merged.items()
        if key.lower() in fields and (value != "" or key.lower() == "opensearch_index_prefix")
    }
    try:
        return OcrSettings(**data)
    except ValidationError as exc:
        missing: list[str] = []
        invalid: list[str] = []
        for err in exc.errors():
            name = str(err["loc"][0]).upper() if err["loc"] else "配置项之间的约束"
            if err["type"] == "missing":
                missing.append(name)
            else:
                invalid.append(f"{name}（{err['msg']}）")
        lines = ["OCR Worker 配置检查失败，无法启动："]
        if missing:
            lines.append(f"  缺少必填环境变量：{', '.join(missing)}")
        if invalid:
            lines.append(f"  取值不合法：{'; '.join(invalid)}")
        lines.append("  请参照项目根目录的 .env.example 设置。")
        raise ConfigError("\n".join(lines)) from exc
