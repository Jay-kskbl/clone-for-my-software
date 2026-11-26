from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx
import psycopg


ROOT = Path(r"C:\Users\lenovo\Desktop\my-software-main\_gh_upload")
OUT = ROOT / "output" / "ocr-search-diagnostic-20261125"
OUT.mkdir(parents=True, exist_ok=True)


def candidate_query(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    groups = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", compact)
    for group in groups:
        if len(group) >= 4:
            return group[:8]
    for group in groups:
        if len(group) >= 2:
            return group[:8]
    raise RuntimeError("No query candidate")


with psycopg.connect(
    host="127.0.0.1",
    port=55433,
    dbname="docmgr",
    user="docmgr",
    password="change-me",
) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id::text, text
            FROM document_chunks
            WHERE source_type = 'ocr'
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()

report: list[dict[str, object]] = []
with httpx.Client(timeout=20.0) as client:
    for document_id, text in rows:
        query = candidate_query(text)
        body = {
            "size": 10,
            "_source": ["document_id", "source_type"],
            "query": {
                "bool": {
                    "must": [{"match": {"text": {"query": query}}}],
                    "filter": [{"terms": {"source_type": ["ocr"]}}],
                }
            },
        }
        response = client.post("http://127.0.0.1:9201/realdata_chunks/_search", json=body)
        response.raise_for_status()
        hits = response.json()["hits"]["hits"]
        report.append(
            {
                "document_id": document_id,
                "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                "query_length": len(query),
                "direct_hit_count": len(hits),
                "direct_target_hit": any(
                    hit["_source"]["document_id"] == document_id for hit in hits
                ),
                "indexed_source_types": sorted(
                    {hit["_source"]["source_type"] for hit in hits}
                ),
            }
        )

(OUT / "report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False, indent=2))
