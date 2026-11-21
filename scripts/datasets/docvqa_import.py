"""下载并转换 DocVQA 500 行示例子集（T24j）。

数据来自 Hugging Face 的 ``vidore/docvqa_test_subsampled``。这里不下载 Parquet，
而是分批调用 datasets-server，并在签名图片地址过期前立即下载。输出符合
``experiments/README.md`` 的 manifest、queries、qrels 和原文件目录结构。

用途仅限打通实验流程和记录性能：查询都是英文，而系统分词器和 CLIP 面向中文，
不能把这里的检索数字当作论文的正式效果结论。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DATASET = "vidore/docvqa_test_subsampled"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE_SIZE = 100
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_RETRIES = 3
SOURCE = "DocVQA via vidore/docvqa_test_subsampled (MIT); images: UCSF Industry Documents Library"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
RAW_KEYS = (
    "questionId",
    "query",
    "question_types",
    "image",
    "docId",
    "image_filename",
    "page",
    "answer",
    "data_split",
    "source",
)
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_-]+$")
REVISION = re.compile(
    r"/cached-assets/vidore/docvqa_test_subsampled/--/([0-9a-f]{40})/--/"
)


class ImportError_(RuntimeError):
    """下载或转换失败。名字加下划线，避免遮蔽 Python 内置 ImportError。"""


class AssetExpired(ImportError_):
    """签名图片地址已过期或暂时不可访问，需要重新取行。"""


@dataclass(frozen=True)
class DocVqaRow:
    question_id: str
    query: str
    doc_id: int
    image_filename: str
    page: str
    width: int
    height: int
    image_src: str
    raw: dict[str, Any]

    @property
    def file_id(self) -> str:
        return "dv_" + self.image_filename

    @property
    def query_id(self) -> str:
        return "dvq_" + self.question_id


@dataclass(frozen=True)
class ImageRecord:
    filename: str
    sha256: str
    bytes: int
    width: int
    height: int
    saved_as: str


@dataclass
class DownloadStats:
    downloaded: int = 0
    skipped: int = 0


def clean_query(text: str) -> tuple[str, bool]:
    """把查询里的制表符和换行替换为空格；第二个返回值表示是否替换过。"""
    cleaned = re.sub(r"[\t\r\n]", " ", text).strip()
    return cleaned, cleaned != text.strip()


def detect_image_extension(data: bytes) -> str:
    """只按文件头接受 PNG/JPEG，不依赖扩展名或原始 Content-Type。"""
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data.startswith(JPEG_SIGNATURE):
        return "jpg"
    raise ImportError_("图片不是 PNG 或 JPEG，不能按任务书转换")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ImportError_(f"数据列 {key} 不是非空字符串：{value!r}")
    return value


def parse_row(raw: Mapping[str, Any]) -> DocVqaRow:
    """校验一行 API 数据，并把签名地址与用于留底的原始列分开。"""
    question_id = _required_str(raw, "questionId")
    query = _required_str(raw, "query")
    image_filename = _required_str(raw, "image_filename")
    page = _required_str(raw, "page")
    if not SAFE_FILENAME.fullmatch(image_filename):
        raise ImportError_(f"image_filename 含不安全字符：{image_filename!r}")
    image = raw.get("image")
    if not isinstance(image, Mapping):
        raise ImportError_("image 列不是对象")
    src = _required_str(image, "src")
    width, height = image.get("width"), image.get("height")
    if (
        not isinstance(width, int)
        or width <= 0
        or not isinstance(height, int)
        or height <= 0
    ):
        raise ImportError_(f"image 宽高不合法：{width!r} x {height!r}")
    doc_id = raw.get("docId")
    if not isinstance(doc_id, int):
        raise ImportError_(f"docId 不是整数：{doc_id!r}")

    # 留底时 image 只留宽高；签名地址不写进任何输出文件。
    saved = {key: raw.get(key) for key in RAW_KEYS}
    saved["image"] = {"height": height, "width": width}
    return DocVqaRow(
        question_id=question_id,
        query=query,
        doc_id=doc_id,
        image_filename=image_filename,
        page=page,
        width=width,
        height=height,
        image_src=src,
        raw=saved,
    )


def rows_by_image(rows: Iterable[DocVqaRow]) -> dict[str, DocVqaRow]:
    """同一图片只保留一行作为下载和 manifest 依据，并检查元数据一致。"""
    chosen: dict[str, DocVqaRow] = {}
    for row in rows:
        previous = chosen.get(row.image_filename)
        if previous is None:
            chosen[row.image_filename] = row
            continue
        identity = (previous.doc_id, previous.page, previous.width, previous.height)
        if identity != (row.doc_id, row.page, row.width, row.height):
            raise ImportError_(
                f"同一 image_filename {row.image_filename} 的元数据不一致："
                f"{identity!r} != {row.doc_id, row.page, row.width, row.height!r}"
            )
    return chosen


def build_manifest(
    rows: Iterable[DocVqaRow], images: Mapping[str, ImageRecord]
) -> list[list[str]]:
    unique = rows_by_image(rows)
    result: list[list[str]] = []
    for filename in sorted(unique):
        row = unique[filename]
        image = images[filename]
        result.append(
            [
                row.file_id,
                image.saved_as,
                "image",
                SOURCE,
                f"docId={row.doc_id}; page={row.page}",
            ]
        )
    return result


def build_queries(rows: Iterable[DocVqaRow]) -> list[list[str]]:
    result = []
    for row in sorted(rows, key=lambda item: item.query_id):
        result.append([row.query_id, "text", clean_query(row.query)[0]])
    return result


def build_qrels(rows: Iterable[DocVqaRow]) -> list[list[str]]:
    return [
        [row.query_id, row.file_id, "3"]
        for row in sorted(rows, key=lambda item: item.query_id)
    ]


def previous_images(root: Path) -> dict[str, ImageRecord]:
    """读取上次 source_rows.jsonl 中可续跑的图片记录。文件损坏时按没有记录处理。"""
    path = root / "datasets" / "source_rows.jsonl"
    if not path.is_file():
        return {}
    result: dict[str, ImageRecord] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            data = json.loads(line)
            filename = data["image_filename"]
            record = ImageRecord(
                filename=filename,
                sha256=str(data["sha256"]),
                bytes=int(data["bytes"]),
                width=int(data["image"]["width"]),
                height=int(data["image"]["height"]),
                saved_as=str(data["saved_as"]),
            )
            if filename in result and result[filename] != record:
                return {}
            result[filename] = record
    except (KeyError, TypeError, ValueError, OSError):
        return {}
    return result


def _existing_file(files_dir: Path, record: ImageRecord) -> Path | None:
    relative = Path(record.saved_as)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    path = files_dir / relative
    return path if path.is_file() else None


def resolve_image(
    row: DocVqaRow,
    files_dir: Path,
    previous: Mapping[str, ImageRecord],
    fetch: Callable[[], bytes],
) -> tuple[ImageRecord, bool]:
    """复用 sha256 一致的文件，否则调用 fetch 下载。返回（记录，是否新下载）。"""
    old = previous.get(row.image_filename)
    if old is not None:
        path = _existing_file(files_dir, old)
        if path is not None:
            data = path.read_bytes()
            if len(data) == old.bytes and sha256_bytes(data) == old.sha256:
                try:
                    if detect_image_extension(data) == path.suffix.lstrip("."):
                        return old, False
                except ImportError_:
                    pass

    data = fetch()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportError_(
            f"{row.image_filename} 超过 UPLOAD_MAX_BYTES：{len(data)} > {MAX_UPLOAD_BYTES}"
        )
    extension = detect_image_extension(data)
    saved_as = f"docvqa/{row.image_filename}.{extension}"
    destination = files_dir / saved_as
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    for other_ext in ("png", "jpg"):
        other = files_dir / "docvqa" / f"{row.image_filename}.{other_ext}"
        if other != destination and other.is_file():
            other.unlink()
    record = ImageRecord(
        filename=row.image_filename,
        sha256=sha256_bytes(data),
        bytes=len(data),
        width=row.width,
        height=row.height,
        saved_as=saved_as,
    )
    return record, True


def _write_delimited(
    path: Path, header: tuple[str, ...], rows: Iterable[list[str]], delimiter: str
):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_outputs(
    root: Path,
    rows: list[DocVqaRow],
    images: Mapping[str, ImageRecord],
) -> None:
    _write_delimited(
        root / "datasets" / "manifest.csv",
        ("file_id", "path", "type", "source", "notes"),
        build_manifest(rows, images),
        ",",
    )
    _write_delimited(
        root / "queries.tsv",
        ("query_id", "type", "text"),
        build_queries(rows),
        "\t",
    )
    _write_delimited(
        root / "qrels" / "docvqa.tsv",
        ("query_id", "file_id", "grade"),
        build_qrels(rows),
        "\t",
    )

    source_rows_path = root / "datasets" / "source_rows.jsonl"
    with source_rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(rows, key=lambda item: item.query_id):
            image = images[row.image_filename]
            entry = dict(row.raw)
            entry.update(
                {
                    "sha256": image.sha256,
                    "bytes": image.bytes,
                    "saved_as": image.saved_as,
                }
            )
            handle.write(
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            )


def request_with_retries(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET 请求失败时最多再重试 3 次；4xx（除 403/410）不重试。"""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.get(url, params=params, follow_redirects=True)
            if response.status_code in {403, 410}:
                raise AssetExpired(f"图片地址已过期（HTTP {response.status_code}）")
            if response.status_code == 429 or response.status_code >= 500:
                raise ImportError_(f"服务暂时不可用（HTTP {response.status_code}）")
            response.raise_for_status()
            return response
        except AssetExpired:
            raise
        except (httpx.HTTPError, ImportError_) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                sleep(0.5 * (2**attempt))
    raise ImportError_(f"请求在重试 {MAX_RETRIES} 次后仍失败：{last_error}")


def fetch_page(client: httpx.Client, offset: int, length: int) -> dict[str, Any]:
    response = request_with_retries(
        client,
        ROWS_URL,
        params={
            "dataset": DATASET,
            "config": "default",
            "split": "test",
            "offset": offset,
            "length": length,
        },
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ImportError_("rows 接口没有返回 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ImportError_("rows 接口应答缺少 rows 数组")
    return payload


def download_bytes(client: httpx.Client, url: str) -> bytes:
    response = request_with_retries(client, url)
    return response.content


def _revision_from_rows(payload: Mapping[str, Any]) -> str | None:
    for item in payload.get("rows", []):
        if not isinstance(item, Mapping):
            continue
        row = item.get("row")
        if not isinstance(row, Mapping):
            continue
        image = row.get("image")
        if isinstance(image, Mapping) and isinstance(image.get("src"), str):
            match = REVISION.search(image["src"])
            if match:
                return match.group(1)
    return None


def import_dataset(
    root: Path,
    *,
    limit: int | None,
    timeout: float,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if limit is not None and limit < 1:
        raise ValueError("--limit 至少为 1")
    started = time.monotonic()
    root.mkdir(parents=True, exist_ok=True)
    files_dir = root / "datasets" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    old_images = previous_images(root)
    images: dict[str, ImageRecord] = {}
    rows: list[DocVqaRow] = []
    stats = DownloadStats()
    revision: str | None = None
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=timeout,
        headers={"User-Agent": "docmgr-docvqa-import/1.0"},
    )

    try:
        offset = 0
        target: int | None = limit
        total_available: int | None = None
        while target is None or offset < target:
            length = PAGE_SIZE if target is None else min(PAGE_SIZE, target - offset)
            payload = fetch_page(active_client, offset, length)
            if revision is None:
                revision = _revision_from_rows(payload)
            total = payload.get("num_rows_total")
            if isinstance(total, int):
                total_available = total
                if target is None:
                    target = total
            page_rows = payload["rows"]
            if not page_rows:
                break

            for local_index, item in enumerate(page_rows[:length]):
                if not isinstance(item, Mapping) or not isinstance(
                    item.get("row"), Mapping
                ):
                    raise ImportError_(f"第 {offset + local_index} 行缺少 row 对象")
                row = parse_row(item["row"])
                rows.append(row)
                if row.image_filename in images:
                    continue

                def fetch(
                    current=row,
                    page_offset=offset,
                    local=local_index,
                    page_length=length,
                ) -> bytes:
                    try:
                        return download_bytes(active_client, current.image_src)
                    except AssetExpired:
                        fresh = fetch_page(active_client, page_offset, page_length)
                        try:
                            fresh_row = parse_row(fresh["rows"][local]["row"])
                        except (IndexError, KeyError, TypeError) as exc:
                            raise ImportError_(
                                "刷新过期图片地址后找不到对应行"
                            ) from exc
                        return download_bytes(active_client, fresh_row.image_src)

                record, downloaded = resolve_image(row, files_dir, old_images, fetch)
                images[row.image_filename] = record
                if downloaded:
                    stats.downloaded += 1
                else:
                    stats.skipped += 1

            offset += len(page_rows[:length])
            if total_available is not None and offset >= total_available:
                break

        if not rows:
            raise ImportError_("接口没有返回任何数据行")
        write_outputs(root, rows, images)
    finally:
        if owned_client:
            active_client.close()

    unique_rows = rows_by_image(rows)
    duplicate_counts = Counter(row.image_filename for row in rows)
    return {
        "rows": len(rows),
        "queries": len(rows),
        "images": len(unique_rows),
        "duplicates": len(rows) - len(unique_rows),
        "duplicated_image_names": sum(
            1 for count in duplicate_counts.values() if count > 1
        ),
        "downloaded": stats.downloaded,
        "skipped": stats.skipped,
        "bytes": sum(record.bytes for record in images.values()),
        "seconds": round(time.monotonic() - started, 3),
        "revision": revision,
    }


def print_summary(summary: Mapping[str, Any]) -> None:
    print("DocVQA 转换完成")
    print(f"  行数: {summary['rows']}")
    print(f"  查询数: {summary['queries']}")
    print(f"  不重复的图片数: {summary['images']}")
    print(f"  重复引用数: {summary['duplicates']}")
    print(f"  出现多次的图片名数: {summary['duplicated_image_names']}")
    print(f"  本次下载数: {summary['downloaded']}")
    print(f"  本次跳过数: {summary['skipped']}")
    print(f"  总字节数: {summary['bytes']}")
    print(f"  耗时: {summary['seconds']} 秒")
    print(f"  数据集修订号: {summary['revision'] or '未从签名地址解析到'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", required=True, type=Path, help="输出实验目录（--root）"
    )
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 行，试跑用")
    parser.add_argument("--timeout", type=float, default=60.0, help="单次请求超时秒数")
    args = parser.parse_args(argv)
    try:
        summary = import_dataset(
            args.out.resolve(),
            limit=args.limit,
            timeout=args.timeout,
        )
    except (ImportError_, ValueError, OSError, httpx.HTTPError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
