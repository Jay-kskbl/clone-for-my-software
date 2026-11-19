"""T24i：reocr 命令挑选要放回队列的 OCR 任务（纯函数，不需要数据库）。

放回队列、条件更新和命令行流程在 tests/integration/test_experiments_db.py。
"""

import argparse
import uuid

from app.modules.experiments import __main__ as cli
from app.modules.experiments.__main__ import reocr_task_ids

V1 = "c1-m500-o50-aaaaaaaaaaaa"
V2 = "c1-m300-o50-bbbbbbbbbbbb"
DOC_A = uuid.uuid4()
DOC_B = uuid.uuid4()


def task(document_id, status, version=V1):
    return (uuid.uuid4(), document_id, {"parse_version": version}, status)


def test_finished_tasks_of_the_current_version_are_selected():
    done = task(DOC_A, "succeeded")
    failed = task(DOC_A, "failed")

    assert reocr_task_ids([done, failed], {DOC_A: V1}) == [done[0], failed[0]]


def test_pending_processing_and_old_version_tasks_are_left_alone():
    tasks = [
        task(DOC_A, "pending"),
        task(DOC_A, "processing"),
        task(DOC_A, "succeeded", version=V2),  # 旧版本：OCR Worker 反正会跳过
    ]

    assert reocr_task_ids(tasks, {DOC_A: V1}) == []


def test_documents_without_a_current_version_are_skipped():
    # 已删除或还没解析成功的文档不在 current_versions 里
    tasks = [task(DOC_B, "succeeded"), (uuid.uuid4(), DOC_A, None, "succeeded")]

    assert reocr_task_ids(tasks, {DOC_A: V1}) == []


def test_reocr_reports_files_that_were_not_imported(tmp_path, capsys):
    root = tmp_path / "experiments"
    (root / "datasets" / "files").mkdir(parents=True)
    (root / "qrels").mkdir()
    (root / "datasets" / "manifest.csv").write_text(
        "file_id,path,type,source,notes\nf1,a.pdf,pdf,自建,\n", encoding="utf-8"
    )
    (root / "queries.tsv").write_text("query_id\ttype\ttext\nq1\ttext\t报销\n", encoding="utf-8")
    (root / "qrels" / "q.tsv").write_text("query_id\tfile_id\tgrade\nq1\tf1\t2\n", encoding="utf-8")

    # 不会碰到数据库：还没导入就先返回
    assert cli.cmd_reocr(argparse.Namespace(yes=True), root, session=None) == 1
    assert "先运行 import" in capsys.readouterr().err
