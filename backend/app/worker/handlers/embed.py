"""embed 任务：图片 → CLIP 服务编码 → image_embeddings → image_vectors 索引（T21）。

由通用 Worker（main 环境）领取：编码本身在 CLIP 服务进程里做（附录 A4），
这里只读文件、发 HTTP 请求、写数据库和索引，不需要深度学习框架。

payload = {"image_id": ...}，由 parse 任务在解析成功的同一事务里创建。

按内容去重（D10）：image_embeddings 以 (sha256, model_name, model_version) 唯一，
已有同内容、同模型的向量就直接用，不再调用 CLIP。
两个任务同时处理内容相同的图片时，用按 sha256 取的事务级咨询锁排队，
后到的那个会看到先到的写好的向量，所以同一内容只编码一次。

文档状态不跟随本任务（D27）：编码失败时文档仍是 succeeded，文件名、正文、OCR 照样可检索，
失败原因记在任务上。
"""

import hashlib

from shared.tasks import Task
from shared.text_index import OpenSearchClient
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Document, ImageAsset, ImageEmbedding
from app.modules.clip import ClipClient, ClipModel, ClipUnavailable, clip_client_from_settings
from app.modules.storage import InvalidStorageKeyError, LocalStorage, StoredFileNotFoundError
from app.modules.vector_index import (
    VECTOR_DIM,
    delete_document_vectors,
    ensure_vector_index,
    index_image_vector,
)
from app.worker.context import task_context
from app.worker.handlers.errors import PipelineError


def _live_document(session: Session, document_id) -> Document | None:
    document = session.get(Document, document_id, populate_existing=True)
    if document is None or document.deleted_at is not None:
        return None
    return document


def _lock_key(sha256: str) -> int:
    # pg_advisory_xact_lock 要一个 bigint：取哈希的前 8 个字节，转成有符号 64 位整数
    return int.from_bytes(hashlib.sha256(sha256.encode()).digest()[:8], "big", signed=True)


def lock_content(session: Session, sha256: str) -> None:
    """在当前事务里对这个内容加锁，提交或回滚时自动释放。"""
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_key(sha256)})


def find_embedding(session: Session, sha256: str, model: ClipModel) -> list[float] | None:
    row = session.scalars(
        select(ImageEmbedding).where(
            ImageEmbedding.sha256 == sha256,
            ImageEmbedding.model_name == model.model_name,
            ImageEmbedding.model_version == model.model_version,
        )
    ).one_or_none()
    if row is None:
        return None
    if row.dim != model.dim or len(row.vector) != model.dim:
        # 同名同版本的模型维度却不同：数据库里的记录坏了，不能拿来用
        raise PipelineError("数据库里这张图片的向量维度与模型不一致，请运行一致性检查")
    return list(row.vector)


def save_embedding(session: Session, sha256: str, model: ClipModel, vector: list[float]) -> None:
    """写入向量；同内容同模型的记录已经存在时什么也不做（唯一约束兜底）。"""
    session.execute(
        insert(ImageEmbedding)
        .values(
            sha256=sha256,
            model_name=model.model_name,
            model_version=model.model_version,
            dim=model.dim,
            vector=vector,
        )
        .on_conflict_do_nothing(index_elements=["sha256", "model_name", "model_version"])
    )


def _read_image(storage: LocalStorage, document: Document) -> bytes:
    try:
        with storage.open(document.storage_key) as fh:
            return fh.read()
    except (StoredFileNotFoundError, InvalidStorageKeyError) as exc:
        raise PipelineError("图片的原始文件不存在或无法读取，无法编码") from exc


def _vector_for(
    session: Session, storage: LocalStorage, clip: ClipClient, document: Document, sha256: str
) -> tuple[ClipModel, list[float]]:
    """取得这张图片在当前模型下的向量：数据库里有就用，没有才调用 CLIP。返回时事务已提交。"""
    model = clip.model()
    if model.dim != VECTOR_DIM:
        # 换了模型而没有重建向量索引：写进去也搜不了，先停下
        raise PipelineError(
            f"CLIP 模型的向量维度是 {model.dim}，向量索引要求 {VECTOR_DIM}；换模型后要重建向量索引"
        )
    lock_content(session, sha256)
    vector = find_embedding(session, sha256, model)
    if vector is None:
        encoded = clip.encode_image(_read_image(storage, document))
        if encoded.model != model:
            # 两次调用之间 CLIP 服务换了模型重启。本次结果不确定属于哪个模型，重试一次即可
            raise ClipUnavailable("CLIP 服务在编码期间更换了模型，稍后重试")
        vector = encoded.vector
        save_embedding(session, sha256, model, vector)
    session.commit()
    return model, vector


def run_embed(
    task: Task,
    *,
    session: Session,
    storage: LocalStorage,
    index: OpenSearchClient,
    clip: ClipClient,
) -> None:
    """处理一个 embed 任务。资源由调用方提供，便于测试。重复执行结果相同。"""
    image_id = task.payload.get("image_id")
    if not isinstance(image_id, str) or not image_id:
        raise PipelineError("embed 任务缺少 image_id")

    document = _live_document(session, task.document_id)
    if document is None:
        # 文档在排队期间被删除了：清理由 cleanup 任务负责
        return
    asset = session.get(ImageAsset, image_id, populate_existing=True)
    if asset is None or asset.document_id != document.id:
        raise PipelineError("找不到这个任务对应的图片记录")
    sha256 = asset.sha256

    model, vector = _vector_for(session, storage, clip, document, sha256)

    # 向量已经存进数据库（对其他同内容的图片也有用）；文档在编码期间被删除的话就不写索引了
    if _live_document(session, task.document_id) is None:
        return

    ensure_vector_index(index)
    index_image_vector(
        index,
        image_id=image_id,
        document_id=document.id,
        sha256=sha256,
        model_name=model.model_name,
        model_version=model.model_version,
        vector=vector,
    )

    if _live_document(session, task.document_id) is None:
        # 编码期间文档被删除，cleanup 任务可能已经先跑完了：把刚写进索引的向量撤掉
        delete_document_vectors(index, task.document_id)


def handle_embed(task: Task) -> None:
    """embed 任务的入口（登记在 registry.HANDLERS，在子进程里执行）。"""
    with task_context() as ctx, clip_client_from_settings(ctx.settings) as clip:
        run_embed(task, session=ctx.session, storage=ctx.storage, index=ctx.index, clip=clip)
