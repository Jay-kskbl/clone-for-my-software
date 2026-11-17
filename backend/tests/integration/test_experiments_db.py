"""T19：实验框架与数据库相关的部分。需要 TEST_DATABASE_URL，未设置时全部跳过。

- 实验账号、运行前检查、版本快照；
- 导入命令（真实上传到临时存储目录）；
- 完整的 run 命令：真实数据库 + 真实检索编排，OpenSearch 用假的网络层按预置结果应答。
  这里得到的数字是合成数据的结果，只证明链路能跑通，不是实验结果。
"""

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from shared.text_index import OpenSearchClient
from sqlalchemy import select

from app.config import Settings
from app.db.models import Document, ExperimentRun, OCRResult, ProcessingTask, SearchLog
from app.modules.experiments import __main__ as cli
from app.modules.experiments.dataset import load_document_map, save_document_map
from app.modules.storage import LocalStorage

V1 = "c1-m500-o50-aaaaaaaaaaaa"


@pytest.fixture
def settings(test_database_url, tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=test_database_url,
        opensearch_url="http://127.0.0.1:1",
        clip_service_url="http://127.0.0.1:1",
        jwt_secret="integration-test-secret-not-used-anywhere-else-0123456789",
        storage_root=tmp_path / "storage",
    )


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "experiments"
    files = root / "datasets" / "files"
    files.mkdir(parents=True)
    (root / "qrels").mkdir()
    (files / "a.pdf").write_bytes(b"%PDF-1.7\nfile a\n")
    (files / "b.pdf").write_bytes(b"%PDF-1.7\nfile b\n")
    (root / "datasets" / "manifest.csv").write_text(
        "file_id,path,type,source,notes\nf1,a.pdf,pdf,自建,\nf2,b.pdf,pdf,自建,\n", encoding="utf-8"
    )
    (root / "queries.tsv").write_text(
        "query_id\ttype\ttext\nq1\ttext\t报销\nq2\ttext\t会议\n", encoding="utf-8"
    )
    (root / "qrels" / "q.tsv").write_text(
        "query_id\tfile_id\tgrade\nq1\tf1\t2\nq2\tf2\t1\n", encoding="utf-8"
    )
    return root


def make_documents(session, owner, *, status="succeeded", version=V1):
    documents = []
    for name in ("a.pdf", "b.pdf"):
        document_id = uuid.uuid4()
        document = Document(
            id=document_id,
            owner_id=owner.id,
            filename=name,
            mime_type="application/pdf",
            size_bytes=1,
            sha256="0" * 64,
            storage_key=f"2026/{document_id}/{'0' * 64}.pdf",
            status=status,
            parse_version=version,
        )
        session.add(document)
        documents.append(document)
    session.commit()
    return documents


def test_experiment_user_is_created_once_as_admin(session):
    first = cli._experiment_user(session, create=True)
    second = cli._experiment_user(session, create=True)

    assert first.id == second.id and first.role == "admin"
    assert cli._experiment_user(session, create=False).id == first.id


def test_preflight_passes_on_a_clean_dataset(session):
    user = cli._experiment_user(session, create=True)
    documents = make_documents(session, user)

    assert cli._preflight(session, [d.id for d in documents]) == []


def test_preflight_reports_every_problem(session):
    user = cli._experiment_user(session, create=True)
    documents = make_documents(session, user, status="processing")
    documents[1].parse_version = "c1-m300-o50-bbbbbbbbbbbb"
    session.add(ProcessingTask(task_type="ocr", document_id=documents[0].id))
    stray = make_documents(session, user)[0]
    stray.deleted_at = datetime.now(UTC)
    session.commit()

    problems = cli._preflight(session, [d.id for d in documents] + [uuid.uuid4()])

    text = "\n".join(problems)
    for expected in [
        "找不到",
        "还没有处理成功",
        "未完成的任务",
        "已删除但还没清理",
        "解析版本不一致",
    ]:
        assert expected in text


def test_version_snapshot_lists_parse_versions_and_ocr_models(session):
    user = cli._experiment_user(session, create=True)
    documents = make_documents(session, user)
    session.add(
        OCRResult(
            document_id=documents[0].id,
            locator={"type": "pdf_page", "page": 1},
            lines=[],
            model_name="PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec",
            model_version="paddleocr-3.7.0/det-afa1820c/rec-2460da90",
        )
    )
    session.commit()

    snapshot = cli._snapshot_versions(session, [d.id for d in documents])

    assert snapshot["parse_versions"] == [V1]
    assert snapshot["ocr_models"] == [
        "PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec paddleocr-3.7.0/det-afa1820c/rec-2460da90"
    ]


def test_import_uploads_once_and_records_the_mapping(session, settings, root):
    assert cli.cmd_import(root, settings, session) == 0
    mapping = load_document_map(root)
    assert set(mapping) == {"f1", "f2"}

    # 第二次导入：内容没变，全部跳过
    assert cli.cmd_import(root, settings, session) == 0
    assert load_document_map(root) == mapping
    assert len(session.scalars(select(Document)).all()) == 2
    # 上传后等待解析，parse 任务已经建好；不加任何标签
    document = session.get(Document, uuid.UUID(mapping["f1"][0]))
    assert document.filename == "a.pdf"
    assert (
        session.scalar(
            select(ProcessingTask).where(ProcessingTask.document_id == document.id)
        ).task_type
        == "parse"
    )
    assert (LocalStorage(settings.storage_root)._root / document.storage_key).exists()


class FakeIndex:
    """按查询文字返回预置的命中文档。"""

    def __init__(self, answers: dict[str, list[str]]) -> None:
        self.answers = answers

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200)
        if request.url.path in ("/", "/_cat/plugins"):
            body = {"version": {"number": "2.19.1"}} if request.url.path == "/" else []
            return httpx.Response(200, json=body)
        body = json.loads(request.content)
        query = body["query"]["bool"]["must"][0]
        text = query.get("match", {}).get("text", {}).get("query") or query.get(
            "multi_match", {}
        ).get("query")
        hits = []
        for rank, document_id in enumerate(self.answers.get(text, [])):
            source = {"document_id": document_id}
            if request.url.path.startswith("/chunks"):
                source.update(
                    chunk_id=f"{document_id}:{V1}:0",
                    source_type="body",
                    locator={"type": "pdf_page", "page": 1},
                    text="片段",
                )
            hits.append({"_source": source, "sort": [10.0 - rank, document_id]})
        return httpx.Response(200, json={"hits": {"hits": hits}})

    def client(self) -> OpenSearchClient:
        return OpenSearchClient(
            "http://search.test:9200",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(self.handle),
        )


def test_full_run_writes_results_metrics_and_an_experiment_row(
    session, settings, root, monkeypatch, tmp_path
):
    user = cli._experiment_user(session, create=True)
    a, b = make_documents(session, user)
    save_document_map({"f1": (str(a.id), "x"), "f2": (str(b.id), "y")}, root)
    config = tmp_path / "B1.json"
    config.write_text(
        json.dumps(
            {
                "name": "B1",
                "channels": {"meta": False, "text": True, "image": False},
                "source_types": ["body"],
                "top_k": 10,
                "ks": [1, 5],
            }
        ),
        encoding="utf-8",
    )
    fake = FakeIndex({"报销": [str(a.id), str(b.id)], "会议": [str(a.id)]})
    monkeypatch.setattr(cli, "client_from_settings", lambda _settings: fake.client())
    args = cli.argparse.Namespace(config=str(config), repeat=2, allow_incomplete=False)

    assert cli.cmd_run(args, root, settings, session) == 0

    (run_dir,) = (root / "runs").iterdir()
    saved = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert saved["experiment"]["name"] == "B1"
    assert saved["search_params"]["rrf_k"] == 60
    assert saved["versions"]["parse_versions"] == [V1]
    assert saved["opensearch"]["version"] == "2.19.1"
    assert saved["complete"] is True
    records = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 4  # 2 条查询 × 2 次
    q1 = next(r for r in records if r["query_id"] == "q1")
    assert [x["file_id"] for x in q1["ranking"]] == ["f1", "f2"]
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    # q1：f1 第 1（相关）；q2：f2 没有返回 → P@1 = (1 + 0) / 2
    assert metrics["overall"]["P@1"]["mean"] == pytest.approx(0.5)
    row = session.scalars(select(ExperimentRun)).one()
    assert row.name == "B1" and row.finished_at is not None
    assert row.raw_results_path.startswith("experiments/runs/")
    # 检索日志照常写，按实验账号可以区分出来
    logs = session.scalars(select(SearchLog)).all()
    assert len(logs) == 4 and {log.user_id for log in logs} == {user.id}


def test_run_refuses_when_preflight_fails(session, settings, root, tmp_path):
    user = cli._experiment_user(session, create=True)
    a, b = make_documents(session, user, status="processing")
    save_document_map({"f1": (str(a.id), "x"), "f2": (str(b.id), "y")}, root)
    args = cli.argparse.Namespace(
        config=str(cli.EXPERIMENTS_DIR / "configs" / "B1.json"), repeat=1, allow_incomplete=False
    )

    assert cli.cmd_run(args, root, settings, session) == 1
    assert not (root / "runs").exists()


def test_run_with_search_service_down_is_incomplete(session, settings, root):
    # settings 里的 OpenSearch 地址指向一个没有服务的端口
    user = cli._experiment_user(session, create=True)
    a, b = make_documents(session, user)
    save_document_map({"f1": (str(a.id), "x"), "f2": (str(b.id), "y")}, root)
    args = cli.argparse.Namespace(
        config=str(cli.EXPERIMENTS_DIR / "configs" / "B1.json"), repeat=1, allow_incomplete=False
    )

    assert cli.cmd_run(args, root, settings, session) == 2

    (run_dir,) = (root / "runs").iterdir()
    records = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(r["ok"] is False for r in records)
    assert json.loads((run_dir / "config.json").read_text(encoding="utf-8"))["complete"] is False
