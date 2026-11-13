"""集中配置：全部从环境变量（或项目根目录的 .env）读取，启动时一次性校验。"""

from pathlib import Path

from pydantic import Field, ValidationError
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

    # ---- 可选 ----
    health_check_timeout_seconds: float = Field(default=2.0, gt=0)


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
            name = str(err["loc"][0]).upper()
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
