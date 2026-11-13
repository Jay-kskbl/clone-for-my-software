"""集中配置：全部从环境变量（或项目根目录的 .env）读取，启动时一次性校验。"""

from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.errors import ConfigError

# backend/app/config.py → 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # extra="ignore"：.env 里还有 docker-compose 用的变量（POSTGRES_* 等），后端不关心
    model_config = SettingsConfigDict(extra="ignore", env_file_encoding="utf-8")

    # ---- 必填 ----
    database_url: str = Field(min_length=1, description="PostgreSQL 连接串")
    opensearch_url: str = Field(min_length=1, description="OpenSearch 地址")
    clip_service_url: str = Field(min_length=1, description="CLIP 模型服务地址")
    # SecretStr：打印配置对象或写日志时显示为 **********，不会泄露
    # 至少 32 个字符：HS256 的密钥长度不应短于 256 位
    jwt_secret: SecretStr = Field(min_length=32, description="签发登录令牌（JWT）的密钥")

    # ---- 可选 ----
    health_check_timeout_seconds: float = Field(default=2.0, gt=0)
    access_token_expire_seconds: int = Field(default=3600, gt=0, description="登录令牌有效期")
    storage_root: Path = Field(
        default=PROJECT_ROOT / "storage", description="上传文件的存储根目录（M3）"
    )

    # ---- Worker（M4，附录 A3）----
    # 租约时长：太短会误回收仍在正常处理的任务，太长则 Worker 崩溃后恢复慢
    worker_lease_seconds: float = Field(default=60.0, gt=0)
    # 续租间隔，必须明显小于租约时长
    worker_heartbeat_seconds: float = Field(default=15.0, gt=0)
    # 队列为空时隔多久再查一次
    worker_poll_seconds: float = Field(default=2.0, gt=0)
    # 单个任务的处理时间上限，超过即终止子进程
    worker_task_timeout_seconds: float = Field(default=600.0, gt=0)
    # 单个任务子进程的内存上限（MB）。只在 Linux 上有效，见 docs/decisions.md D16
    worker_memory_limit_mb: int = Field(default=2048, gt=0)
    # 处理多少个任务后 Worker 主动退出，由外层重新拉起
    worker_max_tasks: int = Field(default=50, gt=0)

    @model_validator(mode="after")
    def _heartbeat_shorter_than_lease(self) -> "Settings":
        # 至少留出两次续租的机会：一次续租因数据库抖动失败，不至于立刻丢掉租约
        if self.worker_heartbeat_seconds * 2 > self.worker_lease_seconds:
            raise ValueError("WORKER_HEARTBEAT_SECONDS 不能超过 WORKER_LEASE_SECONDS 的一半")
        return self

    @field_validator("storage_root")
    @classmethod
    def _storage_root_absolute(cls, value: Path) -> Path:
        # 相对路径一律相对项目根目录，不随启动时的工作目录变化
        return value if value.is_absolute() else PROJECT_ROOT / value


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """读取并校验配置。有问题时抛出 ConfigError，信息里列出每个出错的环境变量。

    env_file=None 表示只读环境变量（测试用）。
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        missing: list[str] = []
        invalid: list[str] = []
        for err in exc.errors():
            # 跨字段的检查（model_validator）没有对应的单个变量，loc 为空
            name = str(err["loc"][0]).upper() if err["loc"] else "配置项之间的约束"
            if err["type"] == "missing":
                missing.append(name)
            else:
                # 不输出变量的值：DATABASE_URL 里可能带密码
                invalid.append(f"{name}（{err['msg']}）")

        lines = ["配置检查失败，后端无法启动："]
        if missing:
            lines.append(f"  缺少必填环境变量：{', '.join(missing)}")
        if invalid:
            lines.append(f"  取值不合法：{'; '.join(invalid)}")
        lines.append("  请参照项目根目录的 .env.example 创建 .env，或直接设置上述环境变量。")
        raise ConfigError("\n".join(lines)) from exc
