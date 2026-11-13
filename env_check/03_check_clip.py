"""第 3 步：Chinese-CLIP 实测（在 CLIP 虚拟环境中运行）。

检查项：
  1. torch / cn_clip 能否导入、版本、可用设备（cpu / mps）
  2. 模型加载耗时与内存、向量维度
  3. 单条查询文本编码延迟 P50/P95（对应查询时的模型服务开销）
  4. 批量图片编码吞吐（张/秒）（对应入库时的向量生成开销）
  5. 合理性检查：用生成的纯色/图形图片，看中文描述能否找回对应图片（只验证链路可用，不是正式评测）
  6. 可选 --hold：加载后保持运行，供 04_mem_snapshot.py 测并发内存

运行：
  .venv-clip/bin/python 03_check_clip.py
  .venv-clip/bin/python 03_check_clip.py --device cpu --model ViT-B-16
  .venv-clip/bin/python 03_check_clip.py --images ~/Desktop/测试图片
  .venv-clip/bin/python 03_check_clip.py --hold

注意：首次运行会把模型权重下载到 env_check/models/。这只在环境实测阶段允许；
正式系统中模型须手动放到配置路径（GLOBAL.md §3.4、§8.2）。
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from _common import ROOT, SAMPLES_DIR, find_cjk_font, peak_rss_mb, percentile, rss_mb, save_result, timer

MODEL_DIR = ROOT / "models"

SANITY = [
    # (文件名, 查询)
    ("clip_red.png", "一张纯红色的图片"),
    ("clip_blue.png", "一张纯蓝色的图片"),
    ("clip_green.png", "一张纯绿色的图片"),
    ("clip_circle.png", "黑色背景上的一个白色圆形"),
    ("clip_text.png", "一张印满黑色文字的白纸"),
]


def make_samples() -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont

    paths = []
    for name, color in [("clip_red.png", (220, 30, 30)), ("clip_blue.png", (30, 60, 220)),
                        ("clip_green.png", (30, 170, 60))]:
        p = SAMPLES_DIR / name
        Image.new("RGB", (320, 320), color).save(p)
        paths.append(p)
    img = Image.new("RGB", (320, 320), (0, 0, 0))
    ImageDraw.Draw(img).ellipse((80, 80, 240, 240), fill=(255, 255, 255))
    p = SAMPLES_DIR / "clip_circle.png"
    img.save(p)
    paths.append(p)
    img = Image.new("RGB", (320, 320), (255, 255, 255))
    d = ImageDraw.Draw(img)
    fp = find_cjk_font()
    font = ImageFont.truetype(fp, 18) if fp else None
    for i in range(12):
        d.text((14, 10 + i * 25), "智能文档管理系统检索模块设计说明" if fp else "document text line " * 2,
               font=font, fill=(0, 0, 0))
    p = SAMPLES_DIR / "clip_text.png"
    img.save(p)
    paths.append(p)
    return paths


def pick_device(req: str):
    import torch

    if req != "auto":
        return req
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ViT-B-16", help="cn_clip 模型名，先测 ViT-B-16")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "mps", "cuda"])
    ap.add_argument("--images", type=Path, help="额外图片文件夹，用于测吞吐")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--hold", action="store_true")
    args = ap.parse_args()

    result: dict = {"errors": [], "model_name": args.model}
    try:
        import torch
        import cn_clip
        import cn_clip.clip as clip
        from cn_clip.clip import load_from_name
        from PIL import Image
    except Exception as e:
        result["errors"].append(f"导入 torch/cn_clip 失败：{e}")
        print(result["errors"][-1])
        save_result("03_clip", result)
        return
    result["torch_version"] = torch.__version__
    result["cn_clip_version"] = getattr(cn_clip, "__version__", "unknown")

    device = pick_device(args.device)
    MODEL_DIR.mkdir(exist_ok=True)
    result["rss_before_load_mb"] = rss_mb()
    try:
        with timer(result, "model_load_s"):
            model, preprocess = load_from_name(args.model, device=device, download_root=str(MODEL_DIR))
            model.eval()
    except Exception as e:
        if device != "cpu":
            result["errors"].append(f"在 {device} 上加载失败，回退 CPU：{str(e)[:200]}")
            device = "cpu"
            with timer(result, "model_load_s"):
                model, preprocess = load_from_name(args.model, device=device, download_root=str(MODEL_DIR))
                model.eval()
        else:
            raise
    result["device"] = device
    result["rss_after_load_mb"] = rss_mb()
    result["model_files"] = sorted(p.name for p in MODEL_DIR.glob("*"))
    print(f"torch {result['torch_version']} / cn_clip {result['cn_clip_version']} / 设备 {device}")
    print(f"模型 {args.model} 加载 {result['model_load_s']} s，内存 {result['rss_after_load_mb']} MB")

    if args.hold:
        print("\n[--hold] 模型已加载，进程保持运行。另开终端运行 04_mem_snapshot.py，完成后按 Ctrl+C 结束。")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    def enc_text(texts):
        with torch.no_grad():
            t = clip.tokenize(texts).to(device)
            f = model.encode_text(t)
            return f / f.norm(dim=-1, keepdim=True)

    def enc_images(paths):
        with torch.no_grad():
            x = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in paths]).to(device)
            f = model.encode_image(x)
            return f / f.norm(dim=-1, keepdim=True)

    samples = make_samples()

    # 向量维度
    f = enc_text(["测试"])
    result["embedding_dim"] = int(f.shape[-1])
    print(f"向量维度 {result['embedding_dim']}")

    # 查询文本编码延迟
    enc_text(["预热"])
    ts = []
    for i in range(args.rounds):
        t = time.perf_counter()
        enc_text([f"会议室里的白板照片 {i}"])
        if device == "mps":
            torch.mps.synchronize()
        ts.append((time.perf_counter() - t) * 1000)
    result["text_encode_ms"] = {"p50": percentile(ts, 50), "p95": percentile(ts, 95), "n": len(ts)}
    print(f"单条查询编码 P50={result['text_encode_ms']['p50']} ms  P95={result['text_encode_ms']['p95']} ms")

    # 批量图片编码吞吐
    pool = list(samples)
    if args.images:
        pool += [p for p in sorted(args.images.expanduser().iterdir())
                 if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}]
    while len(pool) < 32:
        pool += samples
    enc_images(pool[: args.batch])  # 预热
    t = time.perf_counter()
    n = 0
    for i in range(0, len(pool), args.batch):
        enc_images(pool[i: i + args.batch])
        n += len(pool[i: i + args.batch])
    if device == "mps":
        torch.mps.synchronize()
    el = time.perf_counter() - t
    result["image_encode"] = {"images": n, "batch": args.batch, "total_s": round(el, 3),
                              "images_per_s": round(n / el, 2)}
    print(f"图片编码 {n} 张，batch={args.batch}，{result['image_encode']['images_per_s']} 张/秒")

    # 合理性检查
    files = [SAMPLES_DIR / s[0] for s in SANITY]
    queries = [s[1] for s in SANITY]
    img_f = enc_images(files)
    txt_f = enc_text(queries)
    sim = (txt_f @ img_f.T).cpu().tolist()
    sanity = []
    print("\n== 合理性检查（查询 → 最相似图片）==")
    for qi, q in enumerate(queries):
        best = max(range(len(files)), key=lambda j: sim[qi][j])
        ok = best == qi
        sanity.append({"query": q, "expected": files[qi].name, "top1": files[best].name,
                       "correct": ok, "scores": [round(s, 4) for s in sim[qi]]})
        print(f"{'✓' if ok else '✗'} {q:20s} -> {files[best].name}")
    result["sanity"] = sanity
    result["sanity_top1_acc"] = round(sum(s["correct"] for s in sanity) / len(sanity), 3)
    result["peak_rss_mb"] = peak_rss_mb()
    print(f"\n合理性 top1 = {result['sanity_top1_acc']}（仅链路验证），峰值内存 {result['peak_rss_mb']} MB")
    save_result("03_clip", result)


if __name__ == "__main__":
    main()
