"""第 1 步：OpenSearch 实测。

检查项：
  1. 集群是否可达、版本、已安装插件（是否有 k-NN、中文分词插件）
  2. 各中文分词器对同一段中文的切分效果（standard / smartcn / ik_*），供 §4.2 选型
  3. 建一个临时测试索引：BM25 检索 + script_score 精确向量检索（附录 A12）+ 带过滤条件的向量检索
  4. 查询延迟 P50/P95、节点 JVM 堆与进程内存
  5. 结束时删除测试索引（只删除本脚本创建的 envcheck_ 前缀索引）

运行：.venv-main/bin/python 01_check_opensearch.py [--url http://127.0.0.1:9200] [--rounds 50]
只依赖标准库。
"""
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request

from _common import percentile, save_result

INDEX = "envcheck_test"
DIM = 512  # Chinese-CLIP ViT-B/16 的向量维度；实测 CLIP 后若维度不同，以 03 的结果为准

SAMPLE_TEXT = "基于多模态信息检索的智能文档管理系统支持扫描件OCR识别和图文跨模态检索。"
CANDIDATE_ANALYZERS = ["standard", "smartcn", "ik_smart", "ik_max_word"]

DOCS = [
    ("d1", "body", "2024年度财务报告显示营业收入同比增长百分之十二。"),
    ("d1", "body", "报告第三章介绍了成本控制与预算执行情况。"),
    ("d2", "ocr", "发票号码 12345678 开票日期 2024年3月5日 金额 980.00 元"),
    ("d3", "body", "网络工程课程设计：交换机VLAN配置与路由协议实验。"),
    ("d4", "ocr", "会议纪要：讨论智能文档管理系统的检索模块设计。"),
    ("d5", "body", "图像检索采用预训练中文图文模型进行向量化表示。"),
]
QUERIES = ["财务报告", "发票", "路由协议", "检索模块", "图文模型", "预算"]


class OS:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def req(self, method: str, path: str, body=None, ok404=False):
        data = None
        headers = {}
        if body is not None:
            if isinstance(body, str):
                data = body.encode("utf-8")
                headers["Content-Type"] = "application/x-ndjson"
            else:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers["Content-Type"] = "application/json"
        r = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                txt = resp.read().decode("utf-8")
                return json.loads(txt) if txt.strip().startswith(("{", "[")) else txt
        except urllib.error.HTTPError as e:
            if ok404 and e.code == 404:
                return None
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:500]}")


def rand_vec(seed: int) -> list[float]:
    rnd = random.Random(seed)
    v = [rnd.uniform(-1, 1) for _ in range(DIM)]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:9200")
    ap.add_argument("--rounds", type=int, default=50, help="每类查询重复次数，用于计算延迟分位数")
    args = ap.parse_args()
    es = OS(args.url)
    result: dict = {"url": args.url, "errors": []}

    # 1. 连通性与插件
    try:
        info = es.req("GET", "/")
    except Exception as e:
        result["reachable"] = False
        result["errors"].append(f"无法连接 OpenSearch：{e}")
        print(result["errors"][-1])
        print("请先在 opensearch/ 目录执行：docker compose up -d --build，等待约 30–60 秒后重试。")
        save_result("01_opensearch", result)
        return
    result["reachable"] = True
    result["version"] = info["version"]["number"]
    plugins = es.req("GET", "/_cat/plugins?format=json")
    result["plugins"] = sorted({p["component"] for p in plugins})
    print(f"OpenSearch {result['version']}，插件：{', '.join(result['plugins'])}")
    result["has_knn"] = "opensearch-knn" in result["plugins"]

    # 2. 中文分词对比
    print("\n== 中文分词对比 ==")
    print(f"原文：{SAMPLE_TEXT}")
    analyzers = {}
    for a in CANDIDATE_ANALYZERS:
        try:
            r = es.req("POST", "/_analyze", {"analyzer": a, "text": SAMPLE_TEXT})
            tokens = [t["token"] for t in r["tokens"]]
            analyzers[a] = {"available": True, "token_count": len(tokens), "tokens": tokens}
            print(f"[{a:12s}] {len(tokens):3d} 个词：{' / '.join(tokens)}")
        except Exception as e:
            analyzers[a] = {"available": False, "error": str(e)[:200]}
            print(f"[{a:12s}] 不可用")
    result["analyzers"] = analyzers
    chosen = next((a for a in ["ik_max_word", "smartcn"] if analyzers.get(a, {}).get("available")), "standard")
    result["analyzer_used_for_test"] = chosen
    if chosen == "standard":
        result["errors"].append("没有可用的中文分词插件，standard 会按单字切分，BM25 效果会明显偏差")

    # 3. 测试索引
    es.req("DELETE", f"/{INDEX}", ok404=True)
    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {"properties": {
            "document_id": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "text": {"type": "text", "analyzer": chosen},
            "vec": {"type": "knn_vector", "dimension": DIM} if result["has_knn"] else {"type": "float"},
        }},
    }
    if not result["has_knn"]:
        mapping["mappings"]["properties"].pop("vec")
        result["errors"].append("未检测到 opensearch-knn 插件，跳过向量检索测试")
    es.req("PUT", f"/{INDEX}", mapping)

    lines = []
    for i, (doc_id, st, text) in enumerate(DOCS):
        lines.append(json.dumps({"index": {"_index": INDEX, "_id": f"{doc_id}:1:{i}"}}))
        src = {"document_id": doc_id, "source_type": st, "text": text}
        if result["has_knn"]:
            src["vec"] = rand_vec(i)
        lines.append(json.dumps(src, ensure_ascii=False))
    t0 = time.perf_counter()
    es.req("POST", "/_bulk?refresh=true", "\n".join(lines) + "\n")
    result["bulk_index_s"] = round(time.perf_counter() - t0, 4)

    # BM25 正确性
    print("\n== BM25 检索 ==")
    bm25_hits = {}
    for q in QUERIES:
        r = es.req("POST", f"/{INDEX}/_search", {"size": 3, "query": {"match": {"text": q}}})
        hits = [(h["_source"]["document_id"], round(h["_score"], 3)) for h in r["hits"]["hits"]]
        bm25_hits[q] = hits
        print(f"{q:8s} -> {hits}")
    result["bm25_hits"] = bm25_hits

    # 延迟：BM25、精确向量、带过滤的精确向量
    def bench(body) -> list[float]:
        ts = []
        for _ in range(args.rounds):
            t = time.perf_counter()
            es.req("POST", f"/{INDEX}/_search", body)
            ts.append((time.perf_counter() - t) * 1000)
        return ts

    lat = {"bm25_ms": bench({"size": 10, "query": {"match": {"text": "财务报告"}}})}
    if result["has_knn"]:
        qv = rand_vec(999)
        exact = {
            "size": 3,
            "query": {"script_score": {
                "query": {"match_all": {}},
                "script": {"source": "knn_score", "lang": "knn",
                           "params": {"field": "vec", "query_value": qv, "space_type": "cosinesimil"}},
            }},
        }
        try:
            lat["exact_knn_ms"] = bench(exact)
            filtered = json.loads(json.dumps(exact))
            filtered["query"]["script_score"]["query"] = {"terms": {"document_id": ["d1", "d3", "d5"]}}
            r = es.req("POST", f"/{INDEX}/_search", filtered)
            ids = {h["_source"]["document_id"] for h in r["hits"]["hits"]}
            result["filtered_knn_ok"] = ids <= {"d1", "d3", "d5"}
            lat["filtered_exact_knn_ms"] = bench(filtered)
            print(f"\n带权限过滤的精确向量检索只返回允许的文档：{result['filtered_knn_ok']}")
        except Exception as e:
            result["errors"].append(f"精确向量检索失败：{e}")

    result["latency"] = {k: {"p50": percentile(v, 50), "p95": percentile(v, 95), "n": len(v)} for k, v in lat.items()}
    print("\n== 延迟（毫秒，测试索引极小，仅说明链路开销）==")
    for k, v in result["latency"].items():
        print(f"{k:24s} P50={v['p50']}  P95={v['p95']}")

    # 4. 内存
    try:
        st = es.req("GET", "/_nodes/stats/jvm,process,os")
        node = next(iter(st["nodes"].values()))
        result["memory"] = {
            "jvm_heap_used_mb": round(node["jvm"]["mem"]["heap_used_in_bytes"] / 1024**2, 1),
            "jvm_heap_max_mb": round(node["jvm"]["mem"]["heap_max_in_bytes"] / 1024**2, 1),
        }
        print(f"\nJVM 堆：{result['memory']['jvm_heap_used_mb']} / {result['memory']['jvm_heap_max_mb']} MB"
              "（容器总内存请看 `docker stats envcheck-opensearch`）")
    except Exception as e:
        result["errors"].append(f"读取节点内存失败：{e}")

    # 5. 清理（只删除本脚本创建的测试索引）
    es.req("DELETE", f"/{INDEX}", ok404=True)
    save_result("01_opensearch", result)
    if result["errors"]:
        print("\n[需要关注]")
        for e in result["errors"]:
            print(" -", e)


if __name__ == "__main__":
    main()
