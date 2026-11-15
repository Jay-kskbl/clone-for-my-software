"""M8：两个索引的结构（mapping）与创建。

mapping 放在 mappings/ 目录下的 JSON 文件里，纳入版本管理（GLOBAL §3.1、附录 A13）。

分词器只在这两个文件里出现：字段引用的是项目自己起的名字 docmgr_text，
它目前定义为官方插件 analysis-smartcn 提供的 smartcn 分析器（中文分词 + 英文词干 + 停用词），
原样使用，不改它的组成：只依赖 smartcn 这一个名字，出错的可能最小。
以后换分词方案只改这两个文件。

注意：已经建好的索引不会被这里修改。改了 mapping 或分词器之后，
必须删除旧索引、重新创建、再把全部文档重新索引一遍（GLOBAL §11.2），
重建入口由一致性检查（T18）提供。
"""

import json
from pathlib import Path
from typing import Any

from shared.text_index.client import INDEX_NAMES, OpenSearchClient
from shared.text_index.errors import TextIndexError

_MAPPINGS_DIR = Path(__file__).parent / "mappings"
_ALREADY_EXISTS = "resource_already_exists_exception"


def load_index_definition(logical_name: str) -> dict[str, Any]:
    """读出一个索引的 settings + mappings。"""
    if logical_name not in INDEX_NAMES:
        raise ValueError(f"未知的索引：{logical_name!r}")
    return json.loads((_MAPPINGS_DIR / f"{logical_name}.json").read_text(encoding="utf-8"))


def ensure_indices(client: OpenSearchClient) -> list[str]:
    """两个索引不存在就创建，已存在的不动。返回这次新建的索引的逻辑名。

    API 和 Worker 启动时各调用一次；重复调用没有副作用。
    """
    created: list[str] = []
    for logical_name in INDEX_NAMES:
        index = client.index_name(logical_name)
        if client.request("HEAD", f"/{index}", also_accept={404}).status_code != 404:
            continue
        try:
            client.request("PUT", f"/{index}", json=load_index_definition(logical_name))
        except TextIndexError as exc:
            # 两个进程同时启动：另一个抢先建好了。结果一样，不算错
            if _ALREADY_EXISTS in exc.message:
                continue
            raise
        created.append(logical_name)
    return created
