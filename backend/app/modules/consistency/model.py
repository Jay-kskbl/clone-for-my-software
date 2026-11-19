"""M13 一致性检查的数据结构：三方（数据库、磁盘、索引）的快照，以及发现的问题。

ID 一律用字符串保存：索引和磁盘上可能出现不是合法 UUID 的东西，检查时要能如实报告它们。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def locator_key(locator: dict[str, Any]) -> str:
    """来源定位的规范写法，用来比较两个定位是不是同一个对象（键的顺序无关）。"""
    return json.dumps(locator, sort_keys=True, ensure_ascii=False)


# ---- 数据库 ----


@dataclass(frozen=True)
class DbDocument:
    id: str
    deleted: bool
    storage_key: str
    parse_version: str | None
    filename: str
    tags: tuple[str, ...]
    # 有尚未完成（pending / processing）的 cleanup 任务
    cleanup_pending: bool = False
    # 有尚未完成的 parse 或 ocr 任务：片段和索引正在变化中（parse 先写新版本的片段、
    # 最后才改 parse_version，D27），这段时间看到的“不一致”是正常的中间状态
    busy: bool = False
    status: str = "succeeded"
    mime_type: str = "application/pdf"
    # 有尚未完成的 embed 任务：图片向量正在生成（T21），向量类的检查跳过它
    embed_busy: bool = False


@dataclass(frozen=True)
class DbChunk:
    chunk_id: str
    document_id: str
    parse_version: str
    source_type: str
    locator: dict[str, Any]


@dataclass(frozen=True)
class DbOcrResult:
    id: str
    document_id: str
    locator: dict[str, Any]


@dataclass(frozen=True)
class DbImage:
    image_id: str
    document_id: str
    sha256: str


@dataclass(frozen=True)
class DbEmbedding:
    id: str
    sha256: str
    model_name: str
    model_version: str


@dataclass
class DbState:
    documents: dict[str, DbDocument] = field(default_factory=dict)
    chunks: list[DbChunk] = field(default_factory=list)
    ocr_results: list[DbOcrResult] = field(default_factory=list)
    # 每个文档“当前版本”的 ocr 任务所指向的对象（locator_key 的集合）
    ocr_targets: dict[str, set[str]] = field(default_factory=dict)
    # 有 image_assets 记录的文档 → 记录里的 sha256
    image_assets: dict[str, str] = field(default_factory=dict)
    # image_id → 图片（T21：与向量索引对账用）
    images: dict[str, DbImage] = field(default_factory=dict)
    embeddings: list[DbEmbedding] = field(default_factory=list)


# ---- 磁盘 ----


@dataclass(frozen=True)
class DiskFile:
    path: Path
    # 相对存储根目录的路径；是合法 storage_key 时就是 key 本身
    relative: str
    age_seconds: float


@dataclass
class DiskState:
    # 合法 storage_key 形状的文件
    stored: dict[str, DiskFile] = field(default_factory=dict)
    # 临时目录（.tmp/）里的 .part 文件：上传进行中，或进程被强杀后的残留
    temp_files: list[DiskFile] = field(default_factory=list)
    # 其余既不是 storage_key 也不是临时文件的东西（不是本系统写的）
    unknown: list[DiskFile] = field(default_factory=list)


# ---- 索引 ----


@dataclass(frozen=True)
class IndexChunk:
    chunk_id: str
    document_id: str
    parse_version: str


@dataclass(frozen=True)
class IndexVector:
    image_id: str
    document_id: str
    sha256: str
    model_name: str
    model_version: str


@dataclass
class IndexState:
    available: bool = True
    # 检索服务不可用时的原因（不含服务地址）
    error: str | None = None
    # document_id → (文件名, 标签)
    meta: dict[str, tuple[str, tuple[str, ...]]] = field(default_factory=dict)
    chunks: dict[str, IndexChunk] = field(default_factory=dict)
    # image_id → 图片向量索引里的一条（T21）
    vectors: dict[str, IndexVector] = field(default_factory=dict)
    missing_indices: list[str] = field(default_factory=list)
    # 索引名 → 与版本库里的 mapping 不一致的地方
    structure_mismatch: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Snapshot:
    db: DbState
    disk: DiskState
    index: IndexState


# ---- 问题 ----

# 修复类别：repair 命令必须显式列出要修的类别（DEVPLAN T18）
REPAIR_INDEX = "index"  # 按数据库重建单个文档在三个索引里的数据，或撤掉残留
REPAIR_DB_CHUNKS = "db-chunks"  # 删掉数据库里不属于文档当前版本的片段
REPAIR_OCR_RESULTS = "ocr-results"  # 删掉不属于当前版本任何 OCR 对象的识别结果
REPAIR_CLEANUP_TASKS = "cleanup-tasks"  # 为没有清理任务的已删除文档补建 cleanup 任务
REPAIR_TEMP_FILES = "temp-files"  # 删掉过期的上传临时文件
REPAIR_ORPHAN_FILES = "orphan-files"  # 删掉数据库里没有记录的已存储文件
REPAIR_REBUILD_INDICES = "rebuild-indices"  # 删掉三个索引，按版本库的 mapping 重建并全量重新索引
REPAIR_EMBEDDINGS = "embeddings"  # 删掉不再被任何图片引用的向量记录（D10）

REPAIR_KINDS = (
    REPAIR_INDEX,
    REPAIR_DB_CHUNKS,
    REPAIR_OCR_RESULTS,
    REPAIR_CLEANUP_TASKS,
    REPAIR_TEMP_FILES,
    REPAIR_ORPHAN_FILES,
    REPAIR_REBUILD_INDICES,
    REPAIR_EMBEDDINGS,
)


@dataclass(frozen=True)
class Issue:
    kind: str
    detail: str
    document_id: str | None = None
    # 修复类别；None 表示只报告、不提供自动修复（需要人判断）
    repair: str | None = None
    # 修复时需要的目标：文件路径、片段 ID、识别结果 ID 等
    target: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "document_id": self.document_id,
            "detail": self.detail,
            "repair": self.repair,
            "target": self.target,
        }
