"""T11 🧪：zip 炸弹防护（解压后总大小、文件数上限）。"""

import zipfile

import pytest

from app.modules.parsing import ParseError
from app.modules.parsing.zipguard import check_zip_limits

LIMITS = {"max_total_bytes": 1024 * 1024, "max_entries": 10}


def make_zip(path, entries: dict[str, bytes]):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_ordinary_zip_passes(tmp_path):
    path = make_zip(tmp_path / "ok.zip", {"a.xml": b"<a/>", "b.xml": b"x" * 1000})

    check_zip_limits(path, **LIMITS)


def test_zip_bomb_is_rejected_by_total_size(tmp_path):
    # 8 MB 的零压缩后只有几 KB：典型的 zip 炸弹
    path = make_zip(tmp_path / "bomb.zip", {"big.xml": b"\x00" * (8 * 1024 * 1024)})
    assert path.stat().st_size < 100 * 1024

    with pytest.raises(ParseError, match="超过上限") as excinfo:
        check_zip_limits(path, **LIMITS)
    assert excinfo.value.retryable is False


def test_total_size_counts_all_entries_together(tmp_path):
    # 每个条目都不大，加起来超限
    path = make_zip(tmp_path / "many.zip", {f"{i}.xml": b"\x00" * 300_000 for i in range(4)})

    with pytest.raises(ParseError, match="超过上限"):
        check_zip_limits(path, **LIMITS)


def test_size_exactly_at_the_limit_passes(tmp_path):
    path = make_zip(tmp_path / "edge.zip", {"a": b"\x00" * LIMITS["max_total_bytes"]})

    check_zip_limits(path, **LIMITS)


def test_too_many_entries_is_rejected(tmp_path):
    path = make_zip(tmp_path / "files.zip", {f"{i}.xml": b"" for i in range(11)})

    with pytest.raises(ParseError, match="11 个文件"):
        check_zip_limits(path, **LIMITS)


@pytest.mark.parametrize("content", [b"", b"this is not a zip", b"PK\x03\x04" + b"\x00" * 40])
def test_broken_zip_is_rejected(tmp_path, content):
    path = tmp_path / "broken.zip"
    path.write_bytes(content)

    with pytest.raises(ParseError, match="不是完好的 zip"):
        check_zip_limits(path, **LIMITS)


def test_truncated_zip_is_rejected(tmp_path):
    whole = make_zip(tmp_path / "whole.zip", {"a.xml": b"x" * 5000}).read_bytes()
    path = tmp_path / "cut.zip"
    path.write_bytes(whole[: len(whole) // 2])

    with pytest.raises(ParseError, match="不是完好的 zip"):
        check_zip_limits(path, **LIMITS)


def test_encrypted_entry_is_rejected(tmp_path):
    path = make_zip(tmp_path / "enc.zip", {"a.xml": b"secret"})
    data = bytearray(path.read_bytes())
    # 标准库不能写加密的 zip，直接把目录项的“已加密”标志位置 1
    central = data.find(b"PK\x01\x02")
    data[central + 8] |= 0x1
    path.write_bytes(data)

    with pytest.raises(ParseError, match="加密"):
        check_zip_limits(path, **LIMITS)


def test_error_message_does_not_leak_the_server_path(tmp_path):
    path = tmp_path / "broken.zip"
    path.write_bytes(b"nope")

    with pytest.raises(ParseError) as excinfo:
        check_zip_limits(path, **LIMITS)
    assert str(tmp_path) not in excinfo.value.message
