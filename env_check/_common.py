"""环境实测脚本的公共工具：结果保存、计时、内存测量、系统信息。

只依赖标准库；若当前环境装了 psutil 会给出更准确的内存数据。
三个虚拟环境（main / ocr / clip）都会 import 本文件，所以这里不能引入任何第三方必需依赖。
"""
from __future__ import annotations

import json
import os
import platform
import resource
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
SAMPLES_DIR = ROOT / "samples"
RESULTS_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(exist_ok=True)

try:
    import psutil  # type: ignore
except ImportError:  # psutil 是可选的
    psutil = None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def rss_mb() -> float | None:
    """当前进程常驻内存（MB）。没有 psutil 时返回 None。"""
    if psutil is None:
        return None
    return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)


def peak_rss_mb() -> float:
    """进程生命周期内的峰值常驻内存（MB）。

    ru_maxrss 的单位：macOS 为字节，Linux 为 KB —— 这里统一换算。
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(peak / 1024 / 1024, 1)
    return round(peak / 1024, 1)


@contextmanager
def timer(store: dict, key: str):
    """with timer(d, "load_s"): ...  —— 把耗时（秒）写进 d[key]。"""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        store[key] = round(time.perf_counter() - t0, 4)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 4)


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.check_output(["sysctl", "-n", name], text=True).strip()
    except Exception:
        return None


def system_info() -> dict:
    info = {
        "time": now_iso(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "cpu_count": os.cpu_count(),
    }
    if sys.platform == "darwin":
        info["cpu_model"] = _sysctl("machdep.cpu.brand_string")
        mem = _sysctl("hw.memsize")
        if mem:
            info["total_mem_gb"] = round(int(mem) / 1024**3, 1)
    elif psutil is not None:
        info["total_mem_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    if psutil is not None:
        vm = psutil.virtual_memory()
        info["available_mem_gb"] = round(vm.available / 1024**3, 1)
        du = psutil.disk_usage(str(ROOT))
        info["disk_free_gb"] = round(du.free / 1024**3, 1)
    return info


def save_result(name: str, data: dict) -> Path:
    """保存为 results/<name>.json（覆盖上一次），同时保存带时间戳的副本作为原始记录。"""
    data = {"script": name, "saved_at": now_iso(), **data}
    path = RESULTS_DIR / f"{name}.json"
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS_DIR / "history").mkdir(exist_ok=True)
    (RESULTS_DIR / "history" / f"{name}-{stamp}.json").write_text(text, encoding="utf-8")
    print(f"\n[结果已保存] {path}")
    return path


def find_cjk_font() -> str | None:
    """找一个本机可用的中文字体，用于生成带中文的测试图片。"""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def cer(ref: str, hyp: str) -> float:
    """字符错误率 = 编辑距离 / 参考文本长度（忽略空白）。"""
    r = "".join(ref.split())
    h = "".join(hyp.split())
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return round(prev[-1] / len(r), 4)
