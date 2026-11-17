"""实验框架的命令行入口（M12，DEVPLAN T19）。在 backend/ 目录、main 环境下运行：

    python -m app.modules.experiments validate
    python -m app.modules.experiments import
    python -m app.modules.experiments run --config ../experiments/configs/B1.json [--repeat 3]

validate  只检查 experiments/ 下的清单、查询集和标注的格式，不连数据库。
import    以实验专用的管理员账号上传清单里的文件（已导入的按内容哈希跳过），
          生成 datasets/document_map.csv。之后要启动 Worker 完成解析和 OCR。
run       运行一组实验，结果写到 experiments/runs/<时间>_<名称>/，并写一条 experiment_runs 记录。
          运行前检查数据集里的文档是否都已处理成功、有没有待清理的文档；
          不满足时中止，加 --allow-incomplete 可以强行运行（结果里会记录这一点）。

退出码：0 成功；1 出错（配置、数据库、数据集不合法、运行前检查不通过）；
2 运行完成但不完整（有检索失败或本应执行的通道不可用），这样的结果不能当正式数据。
"""

import argparse
import hashlib
import json
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.text_index import client_from_settings
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import load_settings
from app.core.errors import ConfigError, SearchUnavailableError
from app.db.models import Document, ExperimentRun, OCRResult, ProcessingTask, User
from app.db.session import make_engine, make_session_factory
from app.modules.auth import create_user
from app.modules.auth.permissions import ADMIN_ROLE
from app.modules.experiments.config import load_config
from app.modules.experiments.dataset import (
    EXPERIMENTS_DIR,
    DatasetError,
    load_dataset,
    load_document_map,
    save_document_map,
)
from app.modules.experiments.environment import code_versions, machine_info, opensearch_info
from app.modules.experiments.runner import (
    RankedDocument,
    SearchFailed,
    SearchResult,
    run_queries,
)
from app.modules.search import SearchRequestData, params_from_settings, search
from app.modules.storage import LocalStorage

# 实验专用账号：检索日志里靠它与日常使用区分开
EXPERIMENT_USERNAME = "experiment"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _experiment_user(session: Session, *, create: bool) -> User | None:
    user = session.scalar(select(User).where(User.username == EXPERIMENT_USERNAME))
    if user is None and create:
        # 密码随机生成、不保存：这个账号只给命令行用，不需要登录
        user = create_user(session, EXPERIMENT_USERNAME, secrets.token_urlsafe(32), role="admin")
    if user is not None and user.role != ADMIN_ROLE:
        raise SystemExit(f"账号 {EXPERIMENT_USERNAME} 已存在但不是管理员，请换一个名字或手动处理")
    return user


# ---- validate ----


def cmd_validate(root: Path) -> int:
    try:
        dataset = load_dataset(root)
    except DatasetError as exc:
        print(f"数据集有 {len(exc.problems)} 处问题：", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(json.dumps(dataset.summary(), ensure_ascii=False, indent=2))
    return 0


# ---- import ----


def cmd_import(root: Path, settings: Any, session: Session) -> int:
    from app.modules.documents.service import upload_document

    try:
        dataset = load_dataset(root)
    except DatasetError as exc:
        print("数据集不合法，先运行 validate：", *exc.problems, sep="\n  - ", file=sys.stderr)
        return 1
    user = _experiment_user(session, create=True)
    storage = LocalStorage(settings.storage_root)
    mapping = load_document_map(root)
    imported = skipped = 0
    for file in dataset.files.values():
        path = root / "datasets" / "files" / file.path
        sha = _sha256(path)
        existing = mapping.get(file.file_id)
        if existing and existing[1] == sha:
            document = session.get(Document, uuid.UUID(existing[0]))
            if document is not None and document.deleted_at is None:
                skipped += 1
                continue
        with path.open("rb") as stream:
            # 不加标签：标签会参与 B0 的文件名/标签检索，人为加上会影响实验结果
            document = upload_document(
                session,
                storage,
                user,
                stream=stream,
                filename=path.name,
                tags=[],
                limits=_upload_limits(settings),
            )
        mapping[file.file_id] = (str(document.id), sha)
        save_document_map(mapping, root)  # 每导入一个就保存，中途失败也不丢记录
        imported += 1
    print(
        f"导入 {imported} 个文件，跳过 {skipped} 个已导入的。请启动 Worker 和 OCR Worker 完成处理。"
    )
    return 0


def _upload_limits(settings: Any):
    from app.modules.documents.service import UploadLimits

    # 与上传接口（api/documents.py）使用同样的限制：数据集文件和用户上传的文件走同一套校验
    return UploadLimits(
        max_bytes=settings.upload_max_bytes,
        max_filename_chars=settings.upload_max_filename_chars,
        allowed_extensions=settings.upload_allowed_extensions,
    )


# ---- run ----


def _preflight(session: Session, document_ids: list[uuid.UUID]) -> list[str]:
    """运行前检查。返回问题列表（空表示可以运行）。"""
    problems: list[str] = []
    documents = list(session.scalars(select(Document).where(Document.id.in_(document_ids))))
    found = {d.id for d in documents}
    missing = [d for d in document_ids if d not in found]
    if missing:
        problems.append(f"{len(missing)} 个数据集文件在数据库里找不到（重新运行 import）")
    deleted = [d for d in documents if d.deleted_at is not None]
    if deleted:
        problems.append(f"{len(deleted)} 个数据集文件已被删除")
    unfinished = [d for d in documents if d.deleted_at is None and d.status != "succeeded"]
    if unfinished:
        problems.append(
            f"{len(unfinished)} 个数据集文件还没有处理成功（等 Worker 处理完，或查看失败原因）"
        )
    busy = session.scalar(
        select(func.count())
        .select_from(ProcessingTask)
        .where(ProcessingTask.status.in_(("pending", "processing")))
    )
    if busy:
        problems.append(f"还有 {busy} 个未完成的任务（解析、OCR 或清理），结果可能随时变化")
    pending_cleanup = session.scalar(
        select(func.count()).select_from(Document).where(Document.deleted_at.is_not(None))
    )
    if pending_cleanup:
        # D28：管理员检索不做前置过滤，已删除未清理的文档会占通道名次，结果可能少于 top_k
        problems.append(f"有 {pending_cleanup} 个已删除但还没清理的文档，会影响管理员检索的名次")
    versions = {d.parse_version for d in documents if d.deleted_at is None}
    if len(versions) > 1:
        problems.append(f"数据集文件的解析版本不一致：{sorted(map(str, versions))}")
    return problems


def _snapshot_versions(session: Session, document_ids: list[uuid.UUID]) -> dict[str, Any]:
    parse_versions = sorted(
        {
            v
            for v in session.scalars(
                select(Document.parse_version).where(Document.id.in_(document_ids))
            )
            if v
        }
    )
    ocr_models = sorted(
        {
            f"{name} {version}"
            for name, version in session.execute(
                select(OCRResult.model_name, OCRResult.model_version)
                .where(OCRResult.document_id.in_(document_ids))
                .distinct()
            )
        }
    )
    return {"parse_versions": parse_versions, "ocr_models": ocr_models}


def cmd_run(args: argparse.Namespace, root: Path, settings: Any, session: Session) -> int:
    try:
        config = load_config(Path(args.config))
        params = params_from_settings(settings)
        config.check_against(params.max_top_k)
        dataset = load_dataset(root, check_files=False)
    except (ValueError, DatasetError) as exc:
        print(exc, file=sys.stderr)
        return 1

    if not dataset.queries or not dataset.files:
        print("数据集里还没有查询或文件（见 experiments/ 下的模板），无法运行", file=sys.stderr)
        return 1
    user = _experiment_user(session, create=False)
    if user is None:
        print(f"没有实验账号 {EXPERIMENT_USERNAME}，先运行 import", file=sys.stderr)
        return 1
    mapping = load_document_map(root)
    missing = sorted(set(dataset.files) - set(mapping))
    if missing:
        print(f"{len(missing)} 个文件还没有导入（如 {missing[0]}），先运行 import", file=sys.stderr)
        return 1
    document_ids = [uuid.UUID(mapping[f][0]) for f in dataset.files]
    problems = _preflight(session, document_ids)
    if problems:
        print("运行前检查没有通过：", *problems, sep="\n  - ", file=sys.stderr)
        if not args.allow_incomplete:
            return 1
        print("已指定 --allow-incomplete，继续运行；结果里会记录这些问题。", file=sys.stderr)

    started = datetime.now(UTC)
    # 先建好结果目录再跑查询：名字带微秒和随机后缀，连续运行也不会重名；
    # 跑到一半出错时，至少目录和配置已经在，便于追查
    run_dir = (
        root
        / "runs"
        / f"{started.strftime('%Y%m%dT%H%M%S.%fZ')}_{config.name}_{secrets.token_hex(3)}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    client = client_from_settings(settings)
    run_row = ExperimentRun(name=config.name, config={})
    try:

        def do_search(text: str) -> SearchResult:
            try:
                outcome = search(
                    session,
                    user,
                    SearchRequestData(
                        query=text,
                        top_k=config.top_k,
                        channels=dict(config.channels),
                        source_types=list(config.source_types),
                    ),
                    client=client,
                    params=params,
                )
            except SearchUnavailableError as exc:
                raise SearchFailed(exc.message) from exc
            return SearchResult(
                ranking=[
                    RankedDocument(
                        document_id=str(hit.document_id),
                        score=hit.score,
                        channels=[c.model_dump(mode="json") for c in hit.channels],
                    )
                    for hit in outcome.hits
                ],
                took_ms=outcome.took_ms,
                channel_status={r.channel: r.status for r in outcome.channels},
            )

        full_config = {
            "experiment": config.model_dump(mode="json"),
            "search_params": params.to_log(),
            "processing_params": {
                "chunk_max_chars": settings.chunk_max_chars,
                "chunk_overlap_chars": settings.chunk_overlap_chars,
                "pdf_ocr_min_chars": settings.pdf_ocr_min_chars,
            },
            "dataset": dataset.summary(),
            "versions": {**code_versions(), **_snapshot_versions(session, document_ids)},
            "opensearch": opensearch_info(client),
            "machine": machine_info(),
            "preflight_problems": problems,
            "repeats": args.repeat,
            "started_at": started.isoformat(),
        }
        document_to_file = {mapping[f][0]: f for f in dataset.files}
        result = run_queries(config, dataset, document_to_file, do_search, repeats=args.repeat)
    finally:
        client.close()

    full_config["complete"] = result.complete and not problems
    (run_dir / "config.json").write_text(
        json.dumps(full_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for record in result.records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    (run_dir / "metrics.json").write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    run_row.config = full_config
    run_row.metrics = result.metrics
    run_row.raw_results_path = run_dir.relative_to(root.parent).as_posix()
    run_row.finished_at = datetime.now(UTC)
    session.add(run_row)
    session.commit()

    print(f"结果已保存到 {run_dir}")
    overall = result.metrics.get("overall", {})
    for name in sorted(overall):
        mean = overall[name]["mean"]
        shown = "—" if mean is None else f"{mean:.4f}"
        print(f"  {name}: {shown}（{overall[name]['queries']} 条查询）")
    if not full_config["complete"]:
        print("注意：这次运行不完整（有检索失败、通道不可用或运行前检查未通过），不能当正式数据。")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.modules.experiments")
    parser.add_argument(
        "--root",
        type=Path,
        default=EXPERIMENTS_DIR,
        help="实验目录，默认为仓库根目录的 experiments/",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="检查清单、查询集和标注的格式")
    sub.add_parser("import", help="上传数据集文件，生成 document_map.csv")
    run = sub.add_parser("run", help="运行一组实验")
    run.add_argument(
        "--config", required=True, help="实验配置文件，如 ../experiments/configs/B1.json"
    )
    run.add_argument("--repeat", type=int, default=1, help="重复运行几次，默认 1")
    run.add_argument("--allow-incomplete", action="store_true", help="运行前检查不通过时也继续")
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    if args.command == "validate":
        return cmd_validate(root)
    if args.command == "run" and args.repeat < 1:
        parser.error("--repeat 至少为 1")

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine)() as session:
            try:
                if args.command == "import":
                    return cmd_import(root, settings, session)
                return cmd_run(args, root, settings, session)
            except OperationalError as exc:
                print(f"无法连接数据库（{type(exc).__name__}）", file=sys.stderr)
                return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
