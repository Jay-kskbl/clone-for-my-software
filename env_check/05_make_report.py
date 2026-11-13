"""第 5 步：把 results/*.json 汇总成 env_report.md（可直接作为论文"实验环境"一节和附录 A13/A14 决策的依据）。

运行：.venv-main/bin/python 05_make_report.py
"""
from __future__ import annotations

import json

from _common import RESULTS_DIR, ROOT, now_iso


def load(name):
    p = RESULTS_DIR / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def g(d, *keys, default="—"):
    for k in keys:
        if not isinstance(d, dict) or k not in d or d[k] is None:
            return default
        d = d[k]
    return d


def main():
    sysinfo, osr, ocr, clip, mem = (load(n) for n in
                                    ["00_sysinfo", "01_opensearch", "02_ocr", "03_clip", "04_mem_snapshot"])
    L = [f"# 环境实测报告", "", f"生成时间：{now_iso()}", ""]

    L += ["## 1. 硬件与软件环境", ""]
    if sysinfo:
        L += ["| 项目 | 值 |", "|---|---|"]
        for k in ["os", "machine", "cpu_model", "cpu_count", "total_mem_gb", "disk_free_gb", "python"]:
            L.append(f"| {k} | {g(sysinfo, k)} |")
        for k, v in sysinfo.get("tools", {}).items():
            L.append(f"| {k} | {v or '未安装'} |")
    else:
        L.append("未运行 00_sysinfo.py")

    L += ["", "## 2. OpenSearch", ""]
    if osr and osr.get("reachable"):
        L += [f"- 版本：{osr['version']}", f"- 插件：{', '.join(osr['plugins'])}",
              f"- k-NN 插件：{'有' if osr.get('has_knn') else '无'}",
              f"- 测试所用分词器：{osr.get('analyzer_used_for_test')}",
              f"- JVM 堆：{g(osr, 'memory', 'jvm_heap_used_mb')} / {g(osr, 'memory', 'jvm_heap_max_mb')} MB",
              f"- 带权限过滤的精确向量检索结果正确：{g(osr, 'filtered_knn_ok')}", "",
              "**分词对比**", "", "| 分词器 | 可用 | 词数 | 切分结果 |", "|---|---|---|---|"]
        for a, v in osr["analyzers"].items():
            L.append(f"| {a} | {'是' if v['available'] else '否'} | {v.get('token_count', '—')} | "
                     f"{' / '.join(v.get('tokens', []))} |")
        L += ["", "**延迟（毫秒，极小测试索引）**", "", "| 查询 | P50 | P95 |", "|---|---|---|"]
        for k, v in osr.get("latency", {}).items():
            L.append(f"| {k} | {v['p50']} | {v['p95']} |")
    else:
        L.append("不可达或未运行：" + "; ".join((osr or {}).get("errors", ["未运行 01_check_opensearch.py"])))

    L += ["", "## 3. PaddleOCR", ""]
    if ocr and "model_load_s" in ocr:
        L += [f"- paddle {g(ocr, 'paddle_version')} / paddleocr {g(ocr, 'paddleocr_version')} / 设备 {g(ocr, 'paddle_device')}",
              f"- 接口与模型：{g(ocr, 'api')}",
              f"- 模型加载：{ocr['model_load_s']} s；加载后内存：{g(ocr, 'rss_after_load_mb')} MB；峰值：{g(ocr, 'peak_rss_mb')} MB",
              f"- 平均每图耗时：{g(ocr, 'avg_s_per_image')} s；平均 CER：{g(ocr, 'avg_cer')}", "",
              "| 图片 | 平均耗时(s) | CER | 平均置信度 |", "|---|---|---|---|"]
        for i in ocr.get("per_image", []):
            L.append(f"| {i['file']} | {i['avg_s']} | {i.get('cer', '—')} | {i.get('mean_conf', '—')} |")
    else:
        L.append("未完成：" + "; ".join((ocr or {}).get("errors", ["未运行 02_check_ocr.py"])))

    L += ["", "## 4. Chinese-CLIP", ""]
    if clip and "model_load_s" in clip:
        L += [f"- torch {g(clip, 'torch_version')} / cn_clip {g(clip, 'cn_clip_version')} / 设备 {g(clip, 'device')}",
              f"- 模型：{clip['model_name']}；向量维度：{g(clip, 'embedding_dim')}",
              f"- 模型加载：{clip['model_load_s']} s；加载后内存：{g(clip, 'rss_after_load_mb')} MB；峰值：{g(clip, 'peak_rss_mb')} MB",
              f"- 查询文本编码：P50 {g(clip, 'text_encode_ms', 'p50')} ms / P95 {g(clip, 'text_encode_ms', 'p95')} ms",
              f"- 图片编码吞吐：{g(clip, 'image_encode', 'images_per_s')} 张/秒（batch={g(clip, 'image_encode', 'batch')}）",
              f"- 合理性检查 top1：{g(clip, 'sanity_top1_acc')}（仅链路验证，不作为论文检索效果数据）"]
    else:
        L.append("未完成：" + "; ".join((clip or {}).get("errors", ["未运行 03_check_clip.py"])))

    L += ["", "## 5. 并发内存", ""]
    if mem:
        last = mem["snapshots"][-1]
        L += ["| 组件 | 内存(MB) |", "|---|---|"]
        for k in ["opensearch_container_mb", "ocr_worker", "clip_service", "postgres"]:
            L.append(f"| {k} | {last.get(k) or '未检测到'} |")
        L += ["", f"- 系统已用 {last['system_used_gb']} GB，可用 {last['system_available_gb']} GB，swap {last['swap_used_gb']} GB",
              f"- 结论：{mem.get('pressure_note')}"]
    else:
        L.append("未运行 04_mem_snapshot.py")

    L += ["", "## 6. 决策（由 Barry 根据以上数据填写）", "",
          "- [ ] 中文分词方案（附录 A13）：",
          "- [ ] OpenSearch 版本与堆大小：",
          "- [ ] 是否需要启用 OpenSearch 降级预案（附录 A14）：",
          "- [ ] OCR 模型规格（mobile / server）：",
          "- [ ] Chinese-CLIP 模型规格与运行设备：",
          "- [ ] 开发时是否需要按需启停 CLIP 服务：",
          "", "## 7. 错误与警告", ""]
    for name, d in [("opensearch", osr), ("ocr", ocr), ("clip", clip)]:
        for e in (d or {}).get("errors", []):
            L.append(f"- [{name}] {e}")

    out = ROOT / "env_report.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"报告已生成：{out}")


if __name__ == "__main__":
    main()
