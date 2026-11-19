"""M13 一致性检查：对账数据库、磁盘文件、两个文本索引和图片向量索引，报告差异并提供修复与重建入口。

命令行用法见 __main__.py。检索时的数据库二次校验（附录 A10）仍是“删除即时生效”的保证，
本模块负责事后发现并清理残留（GLOBAL §6.9）。
"""

from app.modules.consistency.analyze import DEFAULT_MIN_AGE_SECONDS, analyze
from app.modules.consistency.collect import collect_db, collect_disk, collect_index
from app.modules.consistency.model import REPAIR_KINDS, Issue, Snapshot
from app.modules.consistency.repair import (
    apply,
    plan,
    rebuild_indices,
    reindex_document,
    reindex_document_vectors,
)

__all__ = [
    "DEFAULT_MIN_AGE_SECONDS",
    "REPAIR_KINDS",
    "Issue",
    "Snapshot",
    "analyze",
    "apply",
    "collect_db",
    "collect_disk",
    "collect_index",
    "plan",
    "rebuild_indices",
    "reindex_document",
    "reindex_document_vectors",
]
