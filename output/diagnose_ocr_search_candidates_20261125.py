from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx
import psycopg


ROOT = Path(r"C:\Users\lenovo\Desktop\my-software-main\_gh_upload")
OUT = ROOT / "output" / "ocr-search-diagnostic-20261125-run2"
OUT.mkdir(parents=True, exist_ok=True)


def segments(text: str) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        compact = re.sub(r"\s+", "", line)
        rows.extend(
            group
            for group in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", compact)
        )
    return rows


def direct_hits(client: httpx.Client, query: str) -> list[dict]:
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
    return response.json()["hits"]["hits"]


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
        by_id = client.post(
            "http://127.0.0.1:9201/realdata_chunks/_search",
            json={
                "size": 10,
                "_source": ["document_id", "source_type", "text"],
                "query": {"term": {"document_id": document_id}},
            },
        )
        by_id.raise_for_status()
        id_hits = by_id.json()["hits"]["hits"]
        stored_lengths = [len(hit["_source"].get("text", "")) for hit in id_hits]

        candidates = []
        for segment in segments(text):
            for length in (8, 6, 4, 3, 2):
                if len(segment) < length:
                    continue
                query = segment[:length]
                hits = direct_hits(client, query)
                if hits:
                    candidates.append(
                        {
                            "query_sha256": hashlib.sha256(
                                query.encode("utf-8")
                            ).hexdigest(),
                            "query_length": len(query),
                            "hit_count": len(hits),
                            "target_hit": any(
                                hit["_source"]["document_id"] == document_id
                                for hit in hits
                            ),
                        }
                    )
                    break
            if candidates:
                break

        report.append(
            {
                "document_id": document_id,
                "db_text_length": len(text),
                "indexed_hit_count": len(id_hits),
                "indexed_text_lengths": stored_lengths,
                "working_candidate": candidates[0] if candidates else None,
            }
        )

(OUT / "report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False, indent=2))
