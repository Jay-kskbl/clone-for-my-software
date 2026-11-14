"""解析器测试共用的小工具（不是测试文件）。"""

import struct
import zipfile
from pathlib import Path

# 测试里用的上限：比默认值小得多，这样几 MB 的文件就能触发，不用真的造出几百 MB
ZIP_LIMITS = {"zip_max_total_bytes": 5 * 1024 * 1024, "zip_max_entries": 200}


def rewrite_zip(
    src: Path,
    dst: Path,
    *,
    replace: dict[str, bytes] | None = None,
    drop: set[str] | None = None,
    add: dict[str, bytes] | None = None,
) -> Path:
    """把 src 这个 zip 复制成 dst，中途替换、删除或追加条目。用来从正常文件造出畸形文件。"""
    replace, drop, add = replace or {}, drop or set(), add or {}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename in drop:
                continue
            zout.writestr(info.filename, replace.get(info.filename, zin.read(info.filename)))
        for name, data in add.items():
            zout.writestr(name, data)
    return dst


def forge_declared_size(path: Path, entry: str, declared: int) -> None:
    """把 zip 目录里 entry 的“解压后大小”改成 declared，文件内容不动。

    模拟谎报大小的 zip 炸弹：目录里写得很小，实际数据很大。
    """
    data = bytearray(path.read_bytes())
    name = entry.encode()
    pos = 0
    while (pos := data.find(b"PK\x01\x02", pos)) != -1:  # 中央目录项
        name_len = struct.unpack_from("<H", data, pos + 28)[0]
        if bytes(data[pos + 46 : pos + 46 + name_len]) == name:
            struct.pack_into("<I", data, pos + 24, declared)  # 解压后大小
            path.write_bytes(data)
            return
        pos += 4
    raise AssertionError(f"zip 里没有 {entry}")
