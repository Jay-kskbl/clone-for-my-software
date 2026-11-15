"""M12：评测数据集的读取与校验（DEVPLAN T19，GLOBAL §9.2）。

数据放在仓库根目录的 experiments/ 下：

    datasets/manifest.csv     file_id, path, type, source, notes      （文件清单）
    datasets/files/           原文件，path 相对这个目录                （不进 Git）
    datasets/document_map.csv file_id, document_id, sha256            （导入时生成，不进 Git）
    queries.tsv               query_id, type, text                    （查询集）
    qrels/*.tsv               query_id, file_id, grade                （相关性标注，可分多个文件）

标注用 file_id 而不是 document_id：document_id 要上传后才有，重新导入就会全部改变；
file_id 由标注者自己起，标注可以长期保存。导入时由 document_map.csv 把两者对应起来。
"""

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# backend/app/modules/experiments/dataset.py → 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[4]
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"

FILE_TYPES = ("pdf", "scanned_pdf", "docx", "xlsx", "image")
# 附录 A18：文字型、视觉型、混合型
QUERY_TYPES = ("text", "visual", "mixed")
MAX_GRADE = 3

MANIFEST_COLUMNS = ("file_id", "path", "type", "source", "notes")
QUERY_COLUMNS = ("query_id", "type", "text")
QREL_COLUMNS = ("query_id", "file_id", "grade")
MAP_COLUMNS = ("file_id", "document_id", "sha256")


class DatasetError(Exception):
    """数据集文件有问题。message 里写明是哪个文件、第几行。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class DatasetFile:
    file_id: str
    path: str
    type: str
    source: str
    notes: str


@dataclass(frozen=True)
class Query:
    query_id: str
    type: str
    text: str


@dataclass
class Dataset:
    files: dict[str, DatasetFile] = field(default_factory=dict)
    queries: dict[str, Query] = field(default_factory=dict)
    # query_id → {file_id: 等级}；只记录标注过的，没标注的文件视为不相关（等级 0）
    qrels: dict[str, dict[str, int]] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        return {
            "files": len(self.files),
            "files_by_type": dict(sorted(Counter(f.type for f in self.files.values()).items())),
            "queries": len(self.queries),
            "queries_by_type": dict(sorted(Counter(q.type for q in self.queries.values()).items())),
            "qrels": sum(len(v) for v in self.qrels.values()),
            "relevant_pairs": sum(1 for v in self.qrels.values() for g in v.values() if g > 0),
            "queries_without_relevant": sorted(
                q for q in self.queries if not any(g > 0 for g in self.qrels.get(q, {}).values())
            ),
        }


def _rows(path: Path, columns: tuple[str, ...], delimiter: str, problems: list[str]):
    """逐行产出（行号，字段字典）。表头必须正好是 columns。"""
    if not path.is_file():
        problems.append(f"{path.name}：文件不存在")
        return
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        header = next(reader, None)
        if header is None or tuple(h.strip() for h in header) != columns:
            problems.append(f"{path.name}：表头应为 {delimiter.join(columns)!r}，实际为 {header!r}")
            return
        for number, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row) or row[0].startswith("#"):
                continue
            if len(row) != len(columns):
                problems.append(
                    f"{path.name} 第 {number} 行：应有 {len(columns)} 列，实际 {len(row)} 列"
                )
                continue
            yield number, {c: cell.strip() for c, cell in zip(columns, row, strict=True)}


def load_dataset(root: Path = EXPERIMENTS_DIR, *, check_files: bool = True) -> Dataset:
    """读取并校验整个数据集。有任何问题都收集起来一次报告（DatasetError）。

    check_files：同时检查清单里的原文件是否存在。
    """
    problems: list[str] = []
    dataset = Dataset()

    manifest = root / "datasets" / "manifest.csv"
    files_dir = root / "datasets" / "files"
    for number, row in _rows(manifest, MANIFEST_COLUMNS, ",", problems):
        where = f"manifest.csv 第 {number} 行"
        if not row["file_id"]:
            problems.append(f"{where}：file_id 为空")
            continue
        if row["file_id"] in dataset.files:
            problems.append(f"{where}：file_id {row['file_id']} 重复")
            continue
        if row["type"] not in FILE_TYPES:
            problems.append(f"{where}：type 只能是 {'、'.join(FILE_TYPES)}，实际为 {row['type']!r}")
        relative = Path(row["path"])
        if not row["path"] or relative.is_absolute() or ".." in relative.parts:
            problems.append(f"{where}：path 必须是相对 datasets/files/ 的路径")
        elif check_files and not (files_dir / relative).is_file():
            problems.append(f"{where}：原文件不存在：datasets/files/{row['path']}")
        if not row["source"]:
            problems.append(f"{where}：source 为空（GLOBAL §9.2：数据集要能说明来源）")
        dataset.files[row["file_id"]] = DatasetFile(**row)

    for number, row in _rows(root / "queries.tsv", QUERY_COLUMNS, "\t", problems):
        where = f"queries.tsv 第 {number} 行"
        if not row["query_id"] or not row["text"]:
            problems.append(f"{where}：query_id 和 text 都不能为空")
            continue
        if row["query_id"] in dataset.queries:
            problems.append(f"{where}：query_id {row['query_id']} 重复")
            continue
        if row["type"] not in QUERY_TYPES:
            problems.append(
                f"{where}：type 只能是 {'、'.join(QUERY_TYPES)}，实际为 {row['type']!r}"
            )
        dataset.queries[row["query_id"]] = Query(**row)

    qrel_files = sorted((root / "qrels").glob("*.tsv")) if (root / "qrels").is_dir() else []
    if not qrel_files:
        problems.append("qrels/：没有任何 .tsv 标注文件")
    for qrel_file in qrel_files:
        for number, row in _rows(qrel_file, QREL_COLUMNS, "\t", problems):
            where = f"qrels/{qrel_file.name} 第 {number} 行"
            if row["query_id"] not in dataset.queries:
                problems.append(f"{where}：query_id {row['query_id']} 不在 queries.tsv 里")
            if row["file_id"] not in dataset.files:
                problems.append(f"{where}：file_id {row['file_id']} 不在 manifest.csv 里")
            if not row["grade"].isdigit() or not 0 <= int(row["grade"]) <= MAX_GRADE:
                problems.append(f"{where}：grade 必须是 0 到 {MAX_GRADE} 的整数")
                continue
            grade = int(row["grade"])
            judged = dataset.qrels.setdefault(row["query_id"], {})
            previous = judged.get(row["file_id"])
            if previous is not None and previous != grade:
                problems.append(
                    f"{where}：({row['query_id']}, {row['file_id']}) 已标注为 {previous}，"
                    f"这里又标为 {grade}，两处矛盾"
                )
                continue
            judged[row["file_id"]] = grade

    if problems:
        raise DatasetError(problems)
    return dataset


# ---- file_id ↔ document_id ----


def map_path(root: Path = EXPERIMENTS_DIR) -> Path:
    return root / "datasets" / "document_map.csv"


def load_document_map(root: Path = EXPERIMENTS_DIR) -> dict[str, tuple[str, str]]:
    """file_id → (document_id, sha256)。文件不存在时返回空字典（还没导入过）。"""
    path = map_path(root)
    if not path.is_file():
        return {}
    problems: list[str] = []
    mapping = {
        row["file_id"]: (row["document_id"], row["sha256"])
        for _, row in _rows(path, MAP_COLUMNS, ",", problems)
    }
    if problems:
        raise DatasetError(problems)
    return mapping


def save_document_map(mapping: dict[str, tuple[str, str]], root: Path = EXPERIMENTS_DIR) -> None:
    path = map_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(MAP_COLUMNS)
        for file_id in sorted(mapping):
            writer.writerow([file_id, *mapping[file_id]])
