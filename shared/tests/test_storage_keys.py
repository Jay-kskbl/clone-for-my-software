"""T17：shared/storage_keys.py —— storage_key 的路径安全检查（存储模块与 OCR Worker 共用）。"""

import os
import uuid

import pytest

from shared.storage_keys import InvalidStorageKeyError, resolve_storage_key

# 带字母的 UUID：大写写法与标准写法不同，才能检验“只接受小写”
DOC = uuid.UUID("abcdef12-2222-4333-8444-555555555555")
KEY = f"2026/{DOC}/{'a' * 64}.pdf"


def test_valid_key_resolves_inside_the_root(tmp_path):
    path = resolve_storage_key(tmp_path, KEY)

    assert path == tmp_path.resolve() / KEY
    assert tmp_path.resolve() in path.parents


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        f"2026/{DOC}/{'a' * 64}.exe",
        f"2026/{DOC}/../{'a' * 64}.pdf",
        f"2026/{str(DOC).upper()}/{'a' * 64}.pdf",
        f"2026\\{DOC}\\{'a' * 64}.pdf",
        f"2026/{DOC}/{'a' * 64}.pdf\x00",
        "",
    ],
)
def test_keys_not_generated_by_the_server_are_rejected(tmp_path, key):
    with pytest.raises(InvalidStorageKeyError):
        resolve_storage_key(tmp_path, key)


def test_non_string_key_is_rejected(tmp_path):
    with pytest.raises(InvalidStorageKeyError):
        resolve_storage_key(tmp_path, None)  # type: ignore[arg-type]


def test_symlinked_directory_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    (root / "2026").mkdir(parents=True)
    os.symlink(outside, root / "2026" / str(DOC))

    with pytest.raises(InvalidStorageKeyError, match="之外"):
        resolve_storage_key(root, KEY)


def test_symlinked_file_is_rejected(tmp_path):
    target = tmp_path / "secret"
    target.write_text("x")
    path = tmp_path / KEY
    path.parent.mkdir(parents=True)
    os.symlink(target, path)

    with pytest.raises(InvalidStorageKeyError):
        resolve_storage_key(tmp_path, KEY)
