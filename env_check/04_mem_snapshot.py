"""第 4 步：并发内存快照 —— 回答"四个组件同时跑，这台电脑扛不扛得住"。

步骤：
  终端 A：cd opensearch && docker compose up -d
  终端 B：.venv-ocr/bin/python 02_check_ocr.py --hold
  终端 C：.venv-clip/bin/python 03_check_clip.py --hold
  （如已安装 PostgreSQL，也保持其运行）
  终端 D：.venv-main/bin/python 04_mem_snapshot.py --samples 5

依赖：main 环境中的 psutil。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time

from _common import save_result, system_info

try:
    import psutil
except ImportError:
    raise SystemExit("需要 psutil：.venv-main/bin/pip install psutil")

GROUPS = {
    "ocr_worker": ["02_check_ocr.py"],
    "clip_service": ["03_check_clip.py"],
    "postgres": ["postgres"],
}


def proc_groups() -> dict:
    out = {g: 0.0 for g in GROUPS}
    for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
        try:
            cmd = " ".join(p.info["cmdline"] or []) + " " + (p.info["name"] or "")
            for g, keys in GROUPS.items():
                if any(k in cmd for k in keys):
                    out[g] += p.info["memory_info"].rss / 1024**2
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
    return {k: round(v, 1) for k, v in out.items()}


def docker_mem() -> float | None:
    if shutil.which("docker") is None:
        return None
    try:
        out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", "envcheck-opensearch"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        if not out:
            return None
        usage = json.loads(out)["MemUsage"].split("/")[0].strip()  # 例如 "1.2GiB"
        num = float("".join(c for c in usage if c.isdigit() or c == "."))
        unit = usage.lower()
        if "gib" in unit or "gb" in unit:
            return round(num * 1024, 1)
        if "mib" in unit or "mb" in unit:
            return round(num, 1)
        if "kib" in unit or "kb" in unit:
            return round(num / 1024, 1)
        return num
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    snaps = []
    for i in range(args.samples):
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        s = {
            **proc_groups(),
            "opensearch_container_mb": docker_mem(),
            "system_used_gb": round((vm.total - vm.available) / 1024**3, 2),
            "system_available_gb": round(vm.available / 1024**3, 2),
            "swap_used_gb": round(sw.used / 1024**3, 2),
        }
        snaps.append(s)
        print(f"[{i + 1}/{args.samples}] {s}")
        time.sleep(args.interval)

    last = snaps[-1]
    running = {k: last[k] for k in ["ocr_worker", "clip_service", "postgres", "opensearch_container_mb"]}
    missing = [k for k, v in running.items() if not v]
    result = {"system": system_info(), "snapshots": snaps, "components_not_detected": missing}
    total_mem = result["system"].get("total_mem_gb")
    if total_mem:
        result["pressure_note"] = (
            "可用内存低于 1.5GB 或 swap 持续增长：建议 OpenSearch 堆保持 1g、OCR 用 mobile 模型，"
            "并考虑开发时不同时启动 CLIP 服务"
            if last["system_available_gb"] < 1.5 or last["swap_used_gb"] > 1 else "内存余量正常"
        )
    print("\n未检测到的组件：", missing or "无")
    print("结论：", result.get("pressure_note"))
    save_result("04_mem_snapshot", result)


if __name__ == "__main__":
    main()
