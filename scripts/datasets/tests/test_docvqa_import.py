from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.datasets.docvqa_import import (
    JPEG_SIGNATURE,
    PNG_SIGNATURE,
    DocVqaRow,
    ImageRecord,
    ImportError_,
    build_manifest,
    build_qrels,
    clean_query,
    detect_image_extension,
    parse_row,
    resolve_image,
    sha256_bytes,
    write_outputs,
)


def api_row(
    question_id: str,
    query: str,
    image_filename: str,
    *,
    doc_id: int = 4720,
    page: str = "193",
    width: int = 1653,
    height: int = 2339,
) -> dict:
    return {
        "questionId": question_id,
        "query": query,
        "question_types": None,
        "image": {
            "src": "https://example.invalid/image.jpg?signature=secret",
            "height": height,
            "width": width,
        },
        "docId": doc_id,
        "image_filename": image_filename,
        "page": page,
        "answer": None,
        "data_split": "test",
        "source": "docvqa",
    }


def rows(*items: dict) -> list[DocVqaRow]:
    return [parse_row(item) for item in items]


def records() -> dict[str, ImageRecord]:
    return {
        "rnbx0223": ImageRecord(
            filename="rnbx0223",
            sha256="a" * 64,
            bytes=20,
            width=1653,
            height=2339,
            saved_as="docvqa/rnbx0223.jpg",
        ),
        "rnbx0224": ImageRecord(
            filename="rnbx0224",
            sha256="b" * 64,
            bytes=20,
            width=1653,
            height=2339,
            saved_as="docvqa/rnbx0224.png",
        ),
    }


def test_ids_are_sorted_and_deterministic():
    items = rows(
        api_row("9", "second", "rnbx0224"),
        api_row("10", "first", "rnbx0223"),
    )

    manifest = build_manifest(reversed(items), records())
    queries = build_qrels(items)

    assert [row[0] for row in manifest] == ["dv_rnbx0223", "dv_rnbx0224"]
    assert queries == [
        ["dvq_10", "dv_rnbx0223", "3"],
        ["dvq_9", "dv_rnbx0224", "3"],
    ]


def test_two_queries_share_one_manifest_row_and_two_qrels(tmp_path: Path):
    items = rows(
        api_row("1", "shared page first", "rnbx0223"),
        api_row("2", "shared page second", "rnbx0223"),
    )
    images = {"rnbx0223": records()["rnbx0223"]}

    manifest = build_manifest(items, images)
    qrels = build_qrels(items)
    write_outputs(tmp_path, items, images)

    assert len(manifest) == 1
    assert len(qrels) == 2
    assert (
        len(
            (tmp_path / "datasets" / "manifest.csv")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        == 2
    )
    assert (
        len(
            (tmp_path / "qrels" / "docvqa.tsv").read_text(encoding="utf-8").splitlines()
        )
        == 3
    )


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PNG_SIGNATURE + b"payload", "png"),
        (JPEG_SIGNATURE + b"payload", "jpg"),
    ],
)
def test_png_and_jpeg_headers_are_accepted(data: bytes, expected: str):
    assert detect_image_extension(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF89a" + b"\0" * 20,
        b"RIFF\x10\0\0\0WEBP" + b"\0" * 20,
        b"%PDF-1.7",
    ],
)
def test_other_or_empty_files_are_rejected(data: bytes):
    with pytest.raises(ImportError_):
        detect_image_extension(data)


def test_query_tabs_and_newlines_are_replaced():
    cleaned, changed = clean_query("line one\tline two\r\nline three")

    assert cleaned == "line one line two  line three"
    assert changed is True


def test_csv_with_commas_and_quotes_round_trips_through_experiment_loader(
    tmp_path: Path,
):
    from app.modules.experiments.dataset import load_dataset

    items = rows(
        api_row(
            "1",
            'What is "dividend, 2012"?',
            "rnbx0223",
            page='193, "left"',
        )
    )
    images = {"rnbx0223": records()["rnbx0223"]}
    # 用真实文件字节占位，load_dataset 只检查文件存在，不解析图片。
    destination = tmp_path / "datasets" / "files" / images["rnbx0223"].saved_as
    destination.parent.mkdir(parents=True)
    destination.write_bytes(JPEG_SIGNATURE + b"x")
    write_outputs(tmp_path, items, images)

    dataset = load_dataset(tmp_path)

    assert dataset.files["dv_rnbx0223"].notes == 'docId=4720; page=193, "left"'
    assert dataset.queries["dvq_1"].text == 'What is "dividend, 2012"?'
    assert dataset.qrels["dvq_1"] == {"dv_rnbx0223": 3}


def test_existing_matching_sha_skips_network(tmp_path: Path):
    data = PNG_SIGNATURE + b"same-image"
    filename = "rnbx0223"
    path = tmp_path / "docvqa" / f"{filename}.png"
    path.parent.mkdir()
    path.write_bytes(data)
    previous = {
        filename: ImageRecord(
            filename=filename,
            sha256=sha256_bytes(data),
            bytes=len(data),
            width=1653,
            height=2339,
            saved_as=f"docvqa/{filename}.png",
        )
    }
    row = parse_row(api_row("1", "query", filename))

    record, downloaded = resolve_image(
        row,
        tmp_path,
        previous,
        lambda: pytest.fail("sha256 一致时不应访问网络"),
    )

    assert downloaded is False
    assert record == previous[filename]


def test_source_rows_never_include_signed_image_url(tmp_path: Path):
    items = rows(api_row("1", "query", "rnbx0223"))
    write_outputs(tmp_path, items, {"rnbx0223": records()["rnbx0223"]})

    line = (tmp_path / "datasets" / "source_rows.jsonl").read_text(encoding="utf-8")
    saved = json.loads(line)

    assert "signature=secret" not in line
    assert saved["image"] == {"height": 2339, "width": 1653}
    assert saved["sha256"] == "a" * 64
