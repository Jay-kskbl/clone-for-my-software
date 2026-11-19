"""cleanup 任务：删索引 → 删文件 → 硬删除数据库记录（GLOBAL §3.2 的删除流程）。

索引包括两个文本索引和图片向量索引（T21）。

软删除时文档已经对所有查询不可见（附录 A10），这里做的是真正释放空间。

顺序是有意的：数据库记录最后删。前两步任何一步失败，记录还在，任务重试时
能再找到要删的索引数据和文件；反过来先删记录的话，剩下的就成了没人知道的垃圾。
每一步都可以重复执行：索引里本来就没有、文件本来就不在，都不算错。

硬删除文档记录时，数据库的级联删除会一并删掉它的片段、图片记录、共享、标签关联，
以及它的全部任务记录——包括正在执行的这个 cleanup 任务自己。
"""

from shared.tasks import Task
from shared.text_index import OpenSearchClient, delete_document, ensure_indices
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import Document
from app.modules.storage import LocalStorage
from app.modules.vector_index import delete_document_vectors
from app.worker.context import task_context
from app.worker.handlers.errors import PipelineError


def run_cleanup(
    task: Task, *, session: Session, storage: LocalStorage, index: OpenSearchClient
) -> None:
    """处理一个 cleanup 任务。资源由调用方提供，便于测试。"""
    document = session.get(Document, task.document_id, populate_existing=True)
    if document is None:
        # 上一次执行已经删到最后一步，只是没来得及报告成功
        return
    if document.deleted_at is None:
        # 只清理已经软删除的文档。走到这里说明任务建错了，宁可失败也不删用户的文件
        raise PipelineError("文档没有被删除，拒绝清理")

    # 索引不存在时“按条件删除”会报错；先保证索引在
    ensure_indices(index)
    delete_document(index, document.id)
    # 向量索引不存在时 delete_document_vectors 什么也不做，不必先建。
    # image_embeddings 里的向量不删：可能被内容相同的其他图片共用（D10），由一致性检查清理
    delete_document_vectors(index, document.id)

    # 文件已经不在时 delete 什么也不做（上一次执行可能已经删过）
    storage.delete(document.storage_key)

    # 用 SQL 直接删，依赖数据库的级联删除，不经过 ORM 逐个加载关联对象。
    # 必须是最后一步，之后不能再做任何事：任务记录被级联删除后，
    # 父进程下一次续租会发现记录没了，按“租约丢失”终止本进程。
    session.execute(delete(Document).where(Document.id == document.id))
    session.commit()


def handle_cleanup(task: Task) -> None:
    """cleanup 任务的入口（登记在 registry.HANDLERS，在子进程里执行）。"""
    with task_context() as ctx:
        run_cleanup(task, session=ctx.session, storage=ctx.storage, index=ctx.index)
