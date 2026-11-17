"""T18 🧪：一致性检查。人为制造各类不一致（数据库 / 磁盘 / 索引三方之间），都能被检测出来。

本文件不需要数据库和 OpenSearch：
- 分析部分是纯函数，直接构造三方的快照；
- 磁盘部分用真实的临时目录；
- 索引部分用假的网络层。
数据库的收集与修复见 tests/integration/test_consistency_db.py。
"""

import io
import json
import os
import time
import uuid
from pathlib import Path

import httpx
import pytest
from shared.text_index import OpenSearchClient, load_index_definition

from app.modules.consistency import analyze, collect_disk, collect_index, plan
from app.modules.consistency.model import (
    REPAIR_INDEX,
    REPAIR_KINDS,
    DbChunk,
    DbDocument,
    DbOcrResult,
    DbState,
    DiskFile,
    DiskState,
    IndexChunk,
    IndexState,
    Snapshot,
    locator_key,
)
from app.modules.consistency.repair import RepairReport, _repair_temp_files
from app.modules.storage import LocalStorage

V1 = "c1-m500-o50-aaaaaaaaaaaa"
V2 = "c1-m300-o50-bbbbbbbbbbbb"
OLD = 7200.0  # 足够老：超过默认的 3600 秒
PAGE = {"type": "pdf_page", "page": 1}


def doc_id(n: int) -> str:
    return str(uuid.UUID(int=n))


def key_of(document_id: str) -> str:
    return f"2026/{document_id}/{'0' * 64}.pdf"


def document(n: int, **overrides) -> DbDocument:
    values = {
        "id": doc_id(n),
        "deleted": False,
        "storage_key": key_of(doc_id(n)),
        "parse_version": V1,
        "filename": f"文件{n}.pdf",
        "tags": ("财务",),
        "cleanup_pending": False,
    }
    values.update(overrides)
    return DbDocument(**values)


def chunk(n: int, seq: int, version: str = V1, source_type: str = "body", locator=None) -> DbChunk:
    return DbChunk(
        chunk_id=f"{doc_id(n)}:{version}:{seq}",
        document_id=doc_id(n),
        parse_version=version,
        source_type=source_type,
        locator=locator or PAGE,
    )


def consistent_snapshot() -> Snapshot:
    """两个完全一致的文档：数据库、磁盘、索引三方对得上。"""
    db = DbState(
        documents={doc_id(1): document(1), doc_id(2): document(2)},
        chunks=[chunk(1, 0), chunk(1, 1), chunk(2, 0)],
    )
    disk = DiskState(
        stored={
            key_of(doc_id(n)): DiskFile(Path(key_of(doc_id(n))), key_of(doc_id(n)), OLD)
            for n in (1, 2)
        }
    )
    index = IndexState(
        meta={doc_id(n): (f"文件{n}.pdf", ("财务",)) for n in (1, 2)},
        chunks={
            c.chunk_id: IndexChunk(c.chunk_id, c.document_id, c.parse_version) for c in db.chunks
        },
    )
    return Snapshot(db=db, disk=disk, index=index)


def kinds(issues) -> list[str]:
    return [i.kind for i in issues]


# ---- 一致时什么都不报 ----


def test_consistent_state_has_no_issues():
    assert analyze(consistent_snapshot()) == []


# ---- 🧪 第一类：数据库与磁盘不一致 ----


def test_missing_file_is_detected_but_not_auto_repaired():
    snapshot = consistent_snapshot()
    del snapshot.disk.stored[key_of(doc_id(1))]

    (issue,) = analyze(snapshot)

    assert (issue.kind, issue.document_id, issue.repair) == ("missing_file", doc_id(1), None)


def test_file_without_record_is_detected():
    snapshot = consistent_snapshot()
    stray = key_of(doc_id(99))
    snapshot.disk.stored[stray] = DiskFile(Path(stray), stray, OLD)

    (issue,) = analyze(snapshot)

    assert (issue.kind, issue.target, issue.repair) == ("orphan_file", stray, "orphan-files")


def test_recent_unreferenced_file_is_not_reported():
    # 上传时文件先移到正式路径、再提交数据库（D17）：这一瞬间没有记录是正常的
    snapshot = consistent_snapshot()
    fresh = key_of(doc_id(99))
    snapshot.disk.stored[fresh] = DiskFile(Path(fresh), fresh, 5.0)

    assert analyze(snapshot) == []
    assert kinds(analyze(snapshot, min_age_seconds=1.0)) == ["orphan_file"]


def test_old_temp_files_and_unknown_files_are_detected():
    snapshot = consistent_snapshot()
    snapshot.disk.temp_files = [
        DiskFile(Path("x"), ".tmp/" + "a" * 32 + ".part", OLD),
        DiskFile(Path("y"), ".tmp/" + "b" * 32 + ".part", 10.0),  # 上传进行中
    ]
    snapshot.disk.unknown = [DiskFile(Path("z"), "notes.txt", OLD)]

    issues = analyze(snapshot)

    assert kinds(issues) == ["stale_temp_file", "unknown_file"]
    assert issues[0].repair == "temp-files" and issues[1].repair is None


def test_deleted_document_with_pending_cleanup_is_left_to_the_cleanup_task():
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(1)] = document(1, deleted=True, cleanup_pending=True)
    del snapshot.disk.stored[key_of(doc_id(1))]

    # 文件没了、索引还在：清理任务正在做，不算问题
    assert analyze(snapshot) == []


def test_deleted_document_without_cleanup_task_is_detected():
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(1)] = document(1, deleted=True)

    issues = analyze(snapshot)

    assert kinds(issues) == ["deleted_without_cleanup", "index_deleted"]
    assert [i.repair for i in issues] == ["cleanup-tasks", "index"]


# ---- 🧪 第二类：数据库与索引不一致 ----


def test_index_data_of_a_document_without_record_is_detected():
    # D27 的竞态残留：记录已被硬删除，索引里还有
    snapshot = consistent_snapshot()
    ghost = doc_id(77)
    snapshot.index.chunks[f"{ghost}:{V1}:0"] = IndexChunk(f"{ghost}:{V1}:0", ghost, V1)

    (issue,) = analyze(snapshot)

    assert (issue.kind, issue.document_id, issue.repair) == ("index_orphan", ghost, REPAIR_INDEX)


def test_missing_and_outdated_doc_meta_are_detected():
    snapshot = consistent_snapshot()
    del snapshot.index.meta[doc_id(1)]
    # 改标签时检索服务不可用：数据库里已是新标签，索引还是旧的
    snapshot.db.documents[doc_id(2)] = document(2, tags=("合同", "财务"))

    assert kinds(analyze(snapshot)) == ["doc_meta_missing", "doc_meta_outdated"]


def test_tag_order_does_not_matter():
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(1)] = document(1, tags=("b", "a"))
    snapshot.index.meta[doc_id(1)] = ("文件1.pdf", ("a", "b"))

    assert analyze(snapshot) == []


def test_document_waiting_to_be_parsed_is_not_required_in_doc_meta():
    snapshot = consistent_snapshot()
    # 还在等待解析的文档：doc_meta 由 parse 任务写，现在不在索引里是正常的
    snapshot.db.documents[doc_id(3)] = document(3, parse_version=None, status="pending", busy=True)
    snapshot.disk.stored[key_of(doc_id(3))] = DiskFile(Path("p"), key_of(doc_id(3)), OLD)

    assert analyze(snapshot) == []


def test_failed_document_is_still_required_in_doc_meta():
    """parse 任务在解析之前就写 doc_meta：解析失败的文件仍应能按文件名搜到。"""
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(3)] = document(3, parse_version=None, status="failed")
    snapshot.disk.stored[key_of(doc_id(3))] = DiskFile(Path("p"), key_of(doc_id(3)), OLD)
    snapshot.index.meta[doc_id(3)] = ("文件3.pdf", ("财务",))
    assert analyze(snapshot) == []

    # 例如全量重建索引时漏掉了它，或解析在写 doc_meta 之前就失败了
    del snapshot.index.meta[doc_id(3)]
    issues = analyze(snapshot)
    assert kinds(issues) == ["doc_meta_missing"]
    assert issues[0].repair == REPAIR_INDEX


def test_chunks_missing_from_and_extra_in_the_index_are_detected():
    snapshot = consistent_snapshot()
    del snapshot.index.chunks[f"{doc_id(1)}:{V1}:1"]
    old = f"{doc_id(2)}:{V2}:0"
    snapshot.index.chunks[old] = IndexChunk(old, doc_id(2), V2)

    issues = analyze(snapshot)

    assert [(i.kind, i.document_id) for i in issues] == [
        ("chunks_missing_in_index", doc_id(1)),
        ("chunks_extra_in_index", doc_id(2)),
    ]


def test_missing_index_and_wrong_structure_call_for_a_rebuild():
    snapshot = consistent_snapshot()
    snapshot.index.missing_indices = ["chunks"]
    snapshot.index.structure_mismatch = {
        "doc_meta": ["分词器 docmgr_text 为 standard，应为 smartcn"]
    }

    issues = analyze(snapshot)

    assert kinds(issues)[:2] == ["index_missing", "index_structure_mismatch"]
    assert {i.repair for i in issues[:2]} == {"rebuild-indices"}


def test_unavailable_index_is_not_reported_as_inconsistency():
    snapshot = consistent_snapshot()
    snapshot.index = IndexState(available=False, error="检索服务连接失败")

    # 检索服务连不上时不能把“索引里什么都没有”当成不一致
    assert analyze(snapshot) == []


# ---- 🧪 第三类：数据库内部（片段、识别结果与当前版本）不一致 ----


def test_chunks_of_an_old_version_are_detected():
    snapshot = consistent_snapshot()
    snapshot.db.chunks.append(chunk(1, 1_000_000_000, version=V2, source_type="ocr"))

    issues = analyze(snapshot)

    assert ("db_stale_chunks", doc_id(1), "db-chunks") in [
        (i.kind, i.document_id, i.repair) for i in issues
    ]


def test_ocr_results_are_checked_against_current_ocr_targets():
    snapshot = consistent_snapshot()
    page2 = {"type": "pdf_page", "page": 2}
    snapshot.db.ocr_targets = {doc_id(1): {locator_key(PAGE)}}
    snapshot.db.ocr_results = [
        DbOcrResult(id="r1", document_id=doc_id(1), locator=PAGE),
        DbOcrResult(id="r2", document_id=doc_id(1), locator=page2),  # 旧版本留下的
    ]

    (issue,) = analyze(snapshot)

    assert (issue.kind, issue.target, issue.repair) == ("ocr_result_stale", "r2", "ocr-results")


def test_ocr_chunks_without_a_result_are_reported():
    snapshot = consistent_snapshot()
    ocr_chunk = chunk(2, 1_000_000_000, source_type="ocr")
    snapshot.db.chunks.append(ocr_chunk)
    snapshot.index.chunks[ocr_chunk.chunk_id] = IndexChunk(ocr_chunk.chunk_id, doc_id(2), V1)

    (issue,) = analyze(snapshot)

    assert (issue.kind, issue.repair) == ("ocr_chunks_without_result", None)


def test_many_inconsistencies_at_once_are_all_found():
    snapshot = consistent_snapshot()
    del snapshot.disk.stored[key_of(doc_id(1))]
    ghost = doc_id(77)
    snapshot.index.meta[ghost] = ("幽灵.pdf", ())
    snapshot.db.chunks.append(chunk(2, 5, version=V2))

    assert set(kinds(analyze(snapshot))) == {"missing_file", "index_orphan", "db_stale_chunks"}


def test_result_order_is_stable():
    snapshot = consistent_snapshot()
    del snapshot.index.meta[doc_id(1)]
    del snapshot.index.meta[doc_id(2)]

    assert analyze(snapshot) == analyze(snapshot)


# ---- 修复计划 ----


def test_plan_selects_only_the_requested_kinds_in_execution_order():
    snapshot = consistent_snapshot()
    del snapshot.index.meta[doc_id(1)]
    snapshot.db.chunks.append(chunk(2, 5, version=V2))
    issues = analyze(snapshot)

    assert [i.repair for i in plan(issues, ["index"])] == ["index"]
    # 先改数据库，再按数据库修索引
    assert [i.repair for i in plan(issues, ["index", "db-chunks"])] == ["db-chunks", "index"]
    assert plan(issues, []) == []


def test_unknown_repair_kind_is_rejected():
    with pytest.raises(ValueError, match="未知"):
        plan([], ["everything"])
    assert "rebuild-indices" in REPAIR_KINDS


# ---- 磁盘收集（真实目录）----


def test_disk_scan_classifies_stored_temp_and_unknown_files(tmp_path):
    storage = LocalStorage(tmp_path / "storage")
    stored = storage.put(io.BytesIO(b"%PDF-1.7\n"), document_id=uuid.uuid4())
    root = tmp_path / "storage"
    temp = root / ".tmp" / ("c" * 32 + ".part")
    temp.write_bytes(b"partial")
    (root / "readme.txt").write_text("x")
    (root / "2026" / "not-a-uuid").mkdir(parents=True)
    (root / "2026" / "not-a-uuid" / "f.pdf").write_text("x")

    state = collect_disk(root)

    assert set(state.stored) == {stored.storage_key}
    assert [f.relative for f in state.temp_files] == [temp.relative_to(root.resolve()).as_posix()]
    assert sorted(f.relative for f in state.unknown) == ["2026/not-a-uuid/f.pdf", "readme.txt"]


def test_disk_scan_reports_ages(tmp_path):
    root = tmp_path / "storage"
    LocalStorage(root)
    temp = root / ".tmp" / ("d" * 32 + ".part")
    temp.write_bytes(b"x")
    old = time.time() - 10_000
    os.utime(temp, (old, old))

    (file,) = collect_disk(root).temp_files

    assert file.age_seconds >= 10_000 - 5


def test_symlinks_are_never_treated_as_stored_files(tmp_path):
    root = tmp_path / "storage"
    LocalStorage(root)
    outside = tmp_path / "secret"
    outside.write_text("x")
    link = root / "2026" / str(uuid.uuid4()) / ("e" * 64 + ".pdf")
    link.parent.mkdir(parents=True)
    os.symlink(outside, link)

    state = collect_disk(root)

    assert state.stored == {}
    assert [f.relative for f in state.unknown] == [link.relative_to(root.resolve()).as_posix()]


def test_missing_storage_root_is_an_empty_disk(tmp_path):
    assert collect_disk(tmp_path / "nowhere").stored == {}


def test_temp_file_repair_deletes_only_part_files_in_the_temp_dir(tmp_path):
    root = tmp_path / "storage"
    LocalStorage(root)
    temp = root / ".tmp" / ("f" * 32 + ".part")
    temp.write_bytes(b"x")
    other = root / "keep.txt"
    other.write_text("x")
    report = RepairReport()

    _repair_temp_files(root, [".tmp/" + temp.name, "keep.txt", "../../etc/passwd"], report)

    assert not temp.exists() and other.exists()
    assert len(report.done) == 1 and len(report.skipped) == 2


# ---- 索引收集（假的网络层）----


class FakeOpenSearch:
    def __init__(self) -> None:
        self.docs = {"doc_meta": [], "chunks": []}
        self.missing: set[str] = set()
        self.mappings = {n: load_index_definition(n) for n in ("doc_meta", "chunks")}
        self.down = False
        self.searches = 0

    def _settings(self, name: str) -> dict:
        # OpenSearch 返回的设置值都是字符串
        definition = self.mappings[name]["settings"]
        similarity = {k: str(v) for k, v in definition["index"]["similarity"]["default"].items()}
        return {
            name: {
                "settings": {
                    "index": {
                        "number_of_shards": "1",
                        "similarity": {"default": similarity},
                        "analysis": definition["analysis"],
                    }
                }
            }
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        parts = request.url.path.strip("/").split("/")
        name = parts[0]
        if request.method == "HEAD":
            return httpx.Response(404 if name in self.missing else 200)
        if parts[1:] == ["_mapping"]:
            return httpx.Response(200, json={name: {"mappings": self.mappings[name]["mappings"]}})
        if parts[1:] == ["_settings"]:
            return httpx.Response(200, json=self._settings(name))
        if parts[1:] == ["_search"]:
            self.searches += 1
            body = json.loads(request.content)
            field = next(iter(body["sort"][0]))
            rows = sorted(self.docs[name], key=lambda d: d[field])
            if "search_after" in body:
                rows = [r for r in rows if r[field] > body["search_after"][0]]
            page = rows[: body["size"]]
            hits = [{"_id": r[field], "_source": r, "sort": [r[field]]} for r in page]
            return httpx.Response(200, json={"hits": {"hits": hits}})
        return httpx.Response(
            400, json={"error": {"type": "unexpected", "reason": request.url.path}}
        )

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


def test_index_scan_reads_both_indices():
    server = FakeOpenSearch()
    server.docs["doc_meta"] = [{"document_id": doc_id(1), "filename": "a.pdf", "tags": ["b", "a"]}]
    server.docs["chunks"] = [
        {"chunk_id": f"{doc_id(1)}:{V1}:0", "document_id": doc_id(1), "parse_version": V1}
    ]

    state = collect_index(server.client())

    assert state.available and state.missing_indices == [] and state.structure_mismatch == {}
    assert state.meta == {doc_id(1): ("a.pdf", ("a", "b"))}
    assert list(state.chunks) == [f"{doc_id(1)}:{V1}:0"]


def test_index_scan_pages_through_large_indices(monkeypatch):
    from app.modules.consistency import collect as collect_module

    monkeypatch.setattr(collect_module, "_SCAN_PAGE_SIZE", 3)
    server = FakeOpenSearch()
    server.docs["chunks"] = [
        {"chunk_id": f"{doc_id(1)}:{V1}:{i:02d}", "document_id": doc_id(1), "parse_version": V1}
        for i in range(10)
    ]

    state = collect_index(server.client())

    assert len(state.chunks) == 10
    assert server.searches == 1 + 4  # doc_meta 一页；chunks 3+3+3+1


def test_missing_index_is_reported_not_treated_as_empty():
    server = FakeOpenSearch()
    server.missing = {"chunks"}

    state = collect_index(server.client())

    assert state.available and state.missing_indices == ["chunks"]


def test_structure_differences_are_reported():
    server = FakeOpenSearch()
    server.mappings["chunks"]["mappings"]["properties"]["text"] = {"type": "text"}
    server.mappings["chunks"]["settings"]["analysis"]["analyzer"]["docmgr_text"]["type"] = (
        "standard"
    )
    server.mappings["doc_meta"]["mappings"]["properties"]["owner_id"] = {"type": "keyword"}

    state = collect_index(server.client())

    assert state.structure_mismatch["chunks"] == [
        "字段 text 的定义不同",
        "分词器 docmgr_text 为 standard，应为 smartcn",
    ]
    assert state.structure_mismatch["doc_meta"] == ["多出字段 owner_id"]


def test_unavailable_search_service_is_reported_as_such():
    server = FakeOpenSearch()
    server.down = True

    state = collect_index(server.client())

    assert not state.available
    assert "连接失败" in state.error
    assert state.meta == {} and state.chunks == {}


# ---- 处理中的文档（问题 A：不能把中间状态当成不一致，更不能“修复”它）----


def test_document_being_parsed_is_not_reported_for_chunks_or_index():
    snapshot = consistent_snapshot()
    # parse 已提交新版本的片段（并写进了索引），但还没把 parse_version 改成新版本（D27）
    snapshot.db.documents[doc_id(1)] = document(1, busy=True, status="processing")
    new = chunk(1, 0, version=V2)
    snapshot.db.chunks.append(new)
    snapshot.index.chunks[new.chunk_id] = IndexChunk(new.chunk_id, doc_id(1), V2)

    assert analyze(snapshot) == []


def test_the_same_state_without_a_running_task_is_reported():
    snapshot = consistent_snapshot()
    new = chunk(1, 0, version=V2)
    snapshot.db.chunks.append(new)
    snapshot.index.chunks[new.chunk_id] = IndexChunk(new.chunk_id, doc_id(1), V2)

    assert set(kinds(analyze(snapshot))) == {"db_stale_chunks", "chunks_extra_in_index"}


# ---- 状态与任务、数据是否相符 ----


def test_status_stuck_without_a_task_is_reported():
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(1)] = document(1, status="processing")

    (issue,) = analyze(snapshot)

    assert (issue.kind, issue.repair) == ("status_without_task", None)


def test_succeeded_without_parse_version_is_reported():
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(3)] = document(3, parse_version=None)
    snapshot.disk.stored[key_of(doc_id(3))] = DiskFile(Path("p"), key_of(doc_id(3)), OLD)

    assert kinds(analyze(snapshot)) == ["status_mismatch"]


def test_parsed_image_without_image_asset_is_reported():
    snapshot = consistent_snapshot()
    snapshot.db.documents[doc_id(1)] = document(1, mime_type="image/png")

    assert kinds(analyze(snapshot)) == ["image_asset_missing"]
    snapshot.db.image_assets[doc_id(1)] = "0" * 64
    assert analyze(snapshot) == []


# ---- 重建单个文档的索引 ----


def test_reindex_keeps_doc_meta_of_a_document_without_parse_version(monkeypatch):
    """解析失败（没有解析版本）的文档：没有片段可写，但文件名和标签照样写回 doc_meta，
    否则全量重建之后它就不能按文件名搜到了。"""
    from types import SimpleNamespace

    from app.modules.consistency import repair

    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"deleted": 0})

    client = OpenSearchClient(
        "http://search.test:9200", timeout_seconds=1.0, transport=httpx.MockTransport(handle)
    )
    failed = SimpleNamespace(id=uuid.UUID(int=7), parse_version=None, filename="扫描件.pdf")
    monkeypatch.setattr(repair, "tags_by_document", lambda _session, ids: {ids[0]: ["合同"]})

    written = repair.reindex_document(None, client, failed)

    assert written == 0
    assert not any(r.url.path == "/_bulk" for r in requests)
    meta = next(r for r in requests if r.method == "PUT")
    assert meta.url.path == f"/doc_meta/_doc/{failed.id}"
    assert json.loads(meta.content) == {
        "document_id": str(failed.id),
        "filename": "扫描件.pdf",
        "tags": ["合同"],
    }
