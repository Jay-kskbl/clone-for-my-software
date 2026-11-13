"""关系数据库表结构（GLOBAL §6）。字段说明见 docs/data-model.md。

约定：
- 状态、角色等枚举用 字符串 + CHECK 约束，而不是 PostgreSQL 的 ENUM 类型：以后增减取值只需改约束。
- 时间一律带时区。
- 子表对 documents 的外键都是 ON DELETE CASCADE：硬删除文档记录（清理任务的最后一步）时，
  其片段、任务、OCR 结果等一并删除，不留孤儿数据。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

USER_ROLES = ("user", "admin")
# 文档处理状态与任务状态取值相同（GLOBAL §3.3）
STATUSES = ("pending", "processing", "succeeded", "failed")
SOURCE_TYPES = ("body", "ocr")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _document_fk(**kwargs: Any) -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), **kwargs)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", USER_ROLES), name="role_valid"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), server_default="user")
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in("status", STATUSES), name="status_valid"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # 不级联：有文档的用户不能被直接删除，避免文件记录无主
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # 用户上传时的原始文件名，只用于展示和检索，不参与存储路径
    filename: Mapped[str] = mapped_column(String(255))
    # 按文件魔数识别出的真实类型，不是浏览器上报的
    mime_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    # 当前生效的解析版本；尚未解析成功时为空
    parse_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 软删除标记：非空即对所有查询不可见（GLOBAL §4.5）
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class DocumentShare(Base):
    __tablename__ = "document_shares"

    document_id: Mapped[uuid.UUID] = _document_fk(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = _created_at()


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[uuid.UUID] = _document_fk(primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class ProcessingTask(Base):
    """任务表，同时就是任务队列（附录 A2）。领取逻辑在 T07 实现。"""

    __tablename__ = "processing_tasks"
    __table_args__ = (
        CheckConstraint(_in("status", STATUSES), name="status_valid"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="attempts_valid"),
        # 领取任务的查询按 状态 + 类型 过滤，再按创建时间取最早的
        Index("ix_processing_tasks_claim", "status", "task_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_type: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[uuid.UUID] = _document_fk(index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="3")
    # 失败原因
    error: Mapped[str | None] = mapped_column(Text)
    # 任务参数，例如 OCR 任务要处理的页码
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 租约到期时间：过期仍为 processing 说明 Worker 已崩溃，任务可被回收
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 领取者标识（哪个 Worker 进程）
    claimed_by: Mapped[str | None] = mapped_column(String(128))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint(_in("source_type", SOURCE_TYPES), name="source_type_valid"),
        UniqueConstraint("document_id", "parse_version", "seq"),
    )

    # 确定性 ID：{document_id}:{parse_version}:{seq}（shared.ids.make_chunk_id）
    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[uuid.UUID] = _document_fk()
    parse_version: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(8))
    # 正文存数据库：Word/Excel 预览要显示抽取文本；索引丢失时以数据库为准重建
    text: Mapped[str] = mapped_column(Text)
    # 来源定位，结构见 shared.contracts.SourceLocator
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class ImageAsset(Base):
    __tablename__ = "image_assets"

    # 独立图片：等于 document_id；内嵌图片（P4）：{document_id}:img:{page}:{idx}
    image_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[uuid.UUID] = _document_fk(index=True)
    # 图片内容的哈希，用来关联 image_embeddings（相同内容只编码一次）
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class OCRResult(Base):
    __tablename__ = "ocr_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = _document_fk(index=True)
    # 被识别的对象：PDF 的某一页或一张图片
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 识别出的每一行：文字、四点 bbox、置信度（shared.contracts.OCRLine）
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created_at()


class ImageEmbedding(Base):
    """图片向量。按内容哈希去重，所以不挂 document_id：多个文档可以共用同一条向量。"""

    __tablename__ = "image_embeddings"
    __table_args__ = (
        UniqueConstraint("sha256", "model_name", "model_version"),
        CheckConstraint("dim >= 1", name="dim_positive"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sha256: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(64))
    dim: Mapped[int] = mapped_column(Integer)
    # 向量本体也存数据库：向量索引丢失时可直接重建，不必重新跑 CLIP
    vector: Mapped[list[float]] = mapped_column(ARRAY(REAL))
    created_at: Mapped[datetime] = _created_at()


class SearchLog(Base):
    __tablename__ = "search_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # 用户被删除后日志保留，只是不再关联到人
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    # 本次检索生效的参数（通道开关、RRF k、截断深度等）
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 各通道的执行情况：是否参与、是否降级、耗时
    channels: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 返回的结果列表（document_id、分数、各通道排名）
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    latency_ms: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 运行结束后写入汇总指标；每条查询的原始排名保存在文件里
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_results_path: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
