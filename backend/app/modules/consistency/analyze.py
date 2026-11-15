"""M13：对比三方快照，找出不一致。纯函数，不访问数据库、磁盘和网络。

以数据库为准（decisions.md D9）：数据库记录是唯一依据，磁盘和索引都应当与它一致。

刚发生、还在进行中的变化不算问题：
- 年龄小于 min_age_seconds 的文件不报告——上传时文件先移动到正式路径、再提交数据库（D17），
  这一瞬间文件“没有记录”是正常的；临时文件同理；
- 已软删除、并且有尚未完成的 cleanup 任务的文档，它在磁盘和索引里的数据由清理任务负责，不报告；
- 有尚未完成的 parse 或 ocr 任务的文档（busy），片段和索引正在变化，片段与索引类的检查跳过它：
  parse 先提交新版本的片段、最后才改 parse_version（D27），中间看到的“旧版本片段”其实是新的。
"""

from collections import defaultdict

from app.modules.consistency.model import (
    REPAIR_CLEANUP_TASKS,
    REPAIR_DB_CHUNKS,
    REPAIR_INDEX,
    REPAIR_OCR_RESULTS,
    REPAIR_ORPHAN_FILES,
    REPAIR_REBUILD_INDICES,
    REPAIR_TEMP_FILES,
    Issue,
    Snapshot,
    locator_key,
)

DEFAULT_MIN_AGE_SECONDS = 3600.0


def _disk_issues(snapshot: Snapshot, min_age_seconds: float) -> list[Issue]:
    issues: list[Issue] = []
    documents = snapshot.db.documents
    referenced = {d.storage_key: d for d in documents.values()}

    for document in documents.values():
        if not document.deleted and document.storage_key not in snapshot.disk.stored:
            issues.append(
                Issue(
                    kind="missing_file",
                    document_id=document.id,
                    detail="文档的原始文件不在磁盘上（无法自动修复：只有用户手里有原文件）",
                )
            )

    for key, file in sorted(snapshot.disk.stored.items()):
        if key in referenced or file.age_seconds < min_age_seconds:
            continue
        issues.append(
            Issue(
                kind="orphan_file",
                detail=f"磁盘上的文件在数据库里没有记录：{key}",
                repair=REPAIR_ORPHAN_FILES,
                target=key,
            )
        )

    for file in snapshot.disk.temp_files:
        if file.age_seconds >= min_age_seconds:
            issues.append(
                Issue(
                    kind="stale_temp_file",
                    detail=f"过期的上传临时文件：{file.relative}",
                    repair=REPAIR_TEMP_FILES,
                    target=file.relative,
                )
            )

    for file in snapshot.disk.unknown:
        issues.append(
            Issue(
                kind="unknown_file",
                detail=f"存储目录里有不是本系统写入的东西：{file.relative}（只报告，不处理）",
            )
        )
    return issues


def _deleted_issues(snapshot: Snapshot) -> list[Issue]:
    return [
        Issue(
            kind="deleted_without_cleanup",
            document_id=document.id,
            detail="文档已软删除，但没有进行中的 cleanup 任务，文件和索引数据不会被清理",
            repair=REPAIR_CLEANUP_TASKS,
        )
        for document in snapshot.db.documents.values()
        if document.deleted and not document.cleanup_pending
    ]


def _db_chunk_issues(snapshot: Snapshot) -> list[Issue]:
    issues: list[Issue] = []
    stale: dict[str, int] = defaultdict(int)
    for chunk in snapshot.db.chunks:
        document = snapshot.db.documents.get(chunk.document_id)
        if document is None:  # pragma: no cover —— 外键保证不会发生
            continue
        if document.deleted or document.busy:
            continue  # 已删除的由 cleanup 负责；处理中的片段正在变化
        if chunk.parse_version != document.parse_version:
            stale[chunk.document_id] += 1
    for document_id, count in sorted(stale.items()):
        issues.append(
            Issue(
                kind="db_stale_chunks",
                document_id=document_id,
                detail=(
                    f"数据库里有 {count} 个片段不属于文档当前的解析版本（例如旧版本 OCR 的残留）"
                ),
                repair=REPAIR_DB_CHUNKS,
            )
        )
    return issues


def _ocr_issues(snapshot: Snapshot) -> list[Issue]:
    issues: list[Issue] = []
    results_by_document: dict[str, set[str]] = defaultdict(set)
    for result in snapshot.db.ocr_results:
        document = snapshot.db.documents.get(result.document_id)
        if document is None or document.deleted or document.busy:
            continue
        key = locator_key(result.locator)
        results_by_document[result.document_id].add(key)
        if key not in snapshot.db.ocr_targets.get(result.document_id, set()):
            issues.append(
                Issue(
                    kind="ocr_result_stale",
                    document_id=result.document_id,
                    detail=f"识别结果不属于文档当前版本的任何 OCR 对象：{key}",
                    repair=REPAIR_OCR_RESULTS,
                    target=result.id,
                )
            )

    reported: set[tuple[str, str]] = set()
    for chunk in snapshot.db.chunks:
        document = snapshot.db.documents.get(chunk.document_id)
        if (
            chunk.source_type != "ocr"
            or document is None
            or document.deleted
            or document.busy
            or chunk.parse_version != document.parse_version
        ):
            continue
        key = locator_key(chunk.locator)
        if key in results_by_document[chunk.document_id] or (chunk.document_id, key) in reported:
            continue
        reported.add((chunk.document_id, key))
        issues.append(
            Issue(
                kind="ocr_chunks_without_result",
                document_id=chunk.document_id,
                detail=(
                    f"有 OCR 片段，但没有对应的识别结果：{key}"
                    "（只报告；重新执行该页的 ocr 任务即可）"
                ),
            )
        )
    return issues


def _index_issues(snapshot: Snapshot) -> list[Issue]:
    index = snapshot.index
    if not index.available:
        return []
    issues: list[Issue] = []

    for name in index.missing_indices:
        issues.append(
            Issue(
                kind="index_missing",
                detail=f"索引 {name} 不存在",
                repair=REPAIR_REBUILD_INDICES,
            )
        )
    for name, problems in sorted(index.structure_mismatch.items()):
        issues.append(
            Issue(
                kind="index_structure_mismatch",
                detail=f"索引 {name} 的结构与版本库里的 mapping 不一致：{'；'.join(problems)}",
                repair=REPAIR_REBUILD_INDICES,
            )
        )

    documents = snapshot.db.documents
    indexed_ids = set(index.meta) | {c.document_id for c in index.chunks.values()}
    for document_id in sorted(indexed_ids):
        document = documents.get(document_id)
        if document is None:
            issues.append(
                Issue(
                    kind="index_orphan",
                    document_id=document_id,
                    detail="索引里有这个文档的数据，但数据库里已经没有它的记录",
                    repair=REPAIR_INDEX,
                )
            )
        elif document.deleted and not document.cleanup_pending:
            issues.append(
                Issue(
                    kind="index_deleted",
                    document_id=document_id,
                    detail="文档已删除，但索引里还有它的数据",
                    repair=REPAIR_INDEX,
                )
            )

    db_chunks: dict[str, set[str]] = defaultdict(set)
    for chunk in snapshot.db.chunks:
        document = documents.get(chunk.document_id)
        if document and not document.deleted and chunk.parse_version == document.parse_version:
            db_chunks[chunk.document_id].add(chunk.chunk_id)
    index_chunks: dict[str, set[str]] = defaultdict(set)
    for chunk in index.chunks.values():
        index_chunks[chunk.document_id].add(chunk.chunk_id)

    for document in sorted(documents.values(), key=lambda d: d.id):
        if document.deleted or document.busy:
            continue
        # 还没解析过的文档（parse 任务没跑）不要求在 doc_meta 里：doc_meta 在 parse 任务里写
        if document.parse_version is not None:
            meta = index.meta.get(document.id)
            if meta is None:
                issues.append(
                    Issue(
                        kind="doc_meta_missing",
                        document_id=document.id,
                        detail="文件名与标签不在 doc_meta 索引里，按文件名检索搜不到它",
                        repair=REPAIR_INDEX,
                    )
                )
            elif meta != (document.filename, tuple(sorted(document.tags))):
                issues.append(
                    Issue(
                        kind="doc_meta_outdated",
                        document_id=document.id,
                        detail=(
                            "doc_meta 索引里的文件名或标签与数据库不一致"
                            "（例如改标签时检索服务不可用）"
                        ),
                        repair=REPAIR_INDEX,
                    )
                )
        missing = db_chunks[document.id] - index_chunks[document.id]
        extra = index_chunks[document.id] - db_chunks[document.id]
        if missing:
            issues.append(
                Issue(
                    kind="chunks_missing_in_index",
                    document_id=document.id,
                    detail=f"数据库里有 {len(missing)} 个片段不在 chunks 索引里，这部分内容搜不到",
                    repair=REPAIR_INDEX,
                )
            )
        if extra:
            issues.append(
                Issue(
                    kind="chunks_extra_in_index",
                    document_id=document.id,
                    detail=f"chunks 索引里有 {len(extra)} 个片段不属于文档当前版本（旧版本或残留）",
                    repair=REPAIR_INDEX,
                )
            )
    return issues


_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})


def _status_issues(snapshot: Snapshot) -> list[Issue]:
    """文档状态与任务、数据是否相符。都只报告，不自动修复：需要人看任务的失败原因。"""
    issues: list[Issue] = []
    for document in sorted(snapshot.db.documents.values(), key=lambda d: d.id):
        if document.deleted:
            continue
        if document.status in ("pending", "processing") and not document.busy:
            issues.append(
                Issue(
                    kind="status_without_task",
                    document_id=document.id,
                    detail=(
                        f"文档状态是 {document.status}，但没有进行中的 parse 或 ocr 任务，"
                        "会一直停在这个状态（在任务列表里查看并重试失败的任务）"
                    ),
                )
            )
        if document.status == "succeeded" and document.parse_version is None:
            issues.append(
                Issue(
                    kind="status_mismatch",
                    document_id=document.id,
                    detail="文档状态是 succeeded，但没有解析版本",
                )
            )
        if (
            document.status == "succeeded"
            and document.mime_type in _IMAGE_MIME_TYPES
            and not document.busy
        ):
            recorded = snapshot.db.image_assets.get(document.id)
            if recorded is None:
                issues.append(
                    Issue(
                        kind="image_asset_missing",
                        document_id=document.id,
                        detail="图片文档已解析成功，但没有 image_assets 记录（重新解析即可）",
                    )
                )
    return issues


def analyze(snapshot: Snapshot, *, min_age_seconds: float = DEFAULT_MIN_AGE_SECONDS) -> list[Issue]:
    """找出全部不一致。结果顺序固定，便于比较两次检查的输出。"""
    return [
        *_disk_issues(snapshot, min_age_seconds),
        *_deleted_issues(snapshot),
        *_status_issues(snapshot),
        *_db_chunk_issues(snapshot),
        *_ocr_issues(snapshot),
        *_index_issues(snapshot),
    ]
