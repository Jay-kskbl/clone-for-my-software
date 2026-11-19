"""M12：实验配置（experiments/configs/*.json）。

对照组之间只能通过这几项切换（GLOBAL §9.2：不得为某组实验单独写一套检索代码）。
截断深度、字段权重等检索参数仍来自后端配置（.env），每次运行时原样记录下来。
RRF 的 k 可以由实验配置覆盖（T24 的 k 值消融），不写时用后端配置。
"""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Channel = Literal["meta", "text", "image"]
SourceType = Literal["body", "ocr"]


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    # 三个通道都要写明，不依赖后端的默认开关：配置文件自己就能说明这组实验查了什么
    channels: dict[Channel, bool]
    source_types: list[SourceType] = Field(default=["body", "ocr"], min_length=1)
    # 每条查询取多少个文件。必须不小于最大的 K，且不超过后端的 SEARCH_MAX_TOP_K
    top_k: int = Field(default=20, ge=1)
    ks: list[int] = Field(default=[5, 10, 20], min_length=1)
    # 覆盖后端的 SEARCH_RRF_K（只影响这次实验，不影响 API）。None 表示用后端配置
    rrf_k: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def _safe_name(cls, value: str) -> str:
        # 名字会出现在结果目录名里
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("只能包含字母、数字、'_'、'.'、'-'")
        return value

    @field_validator("channels")
    @classmethod
    def _all_channels(cls, value: dict[str, bool]) -> dict[str, bool]:
        if set(value) != {"meta", "text", "image"}:
            raise ValueError("meta、text、image 三个通道都要写明 true 或 false")
        if not any(value.values()):
            raise ValueError("至少要开启一个通道")
        return value

    @field_validator("ks")
    @classmethod
    def _positive_ks(cls, value: list[int]) -> list[int]:
        if any(k < 1 for k in value):
            raise ValueError("K 必须是正整数")
        return sorted(set(value))

    def check_against(self, max_top_k: int) -> None:
        if max(self.ks) > self.top_k:
            raise ValueError(f"top_k（{self.top_k}）不能小于最大的 K（{max(self.ks)}）")
        if self.top_k > max_top_k:
            raise ValueError(f"top_k（{self.top_k}）超过了后端的 SEARCH_MAX_TOP_K（{max_top_k}）")


def load_config(path: Path) -> ExperimentConfig:
    try:
        return ExperimentConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"实验配置 {path.name} 无法读取或不合法：{exc}") from exc
