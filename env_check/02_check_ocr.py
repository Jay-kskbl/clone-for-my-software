"""第 2 步：PaddleOCR 实测（在 OCR 虚拟环境中运行）。

检查项：
  1. paddle / paddleocr 能否导入、版本、可用设备
  2. 模型加载耗时、加载后内存
  3. 用生成的中文测试图（已知标准文本）测识别耗时与字符错误率 CER
  4. 可选：用你自己的图片测耗时（同名 .txt 若存在则一并计算 CER）
  5. 可选 --hold：加载完模型后保持进程不退出，用于 04_mem_snapshot.py 测并发内存

运行：
  .venv-ocr/bin/python 02_check_ocr.py
  .venv-ocr/bin/python 02_check_ocr.py --images ~/Desktop/测试图片 --mobile
  .venv-ocr/bin/python 02_check_ocr.py --hold

注意：PaddleOCR 首次运行会自动下载模型（约数十到上百 MB）。这只在环境实测阶段允许；
正式系统中模型须手动放到配置路径（GLOBAL.md §3.4、§8.2）。请把下载到的模型名称记录在报告里。
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from _common import SAMPLES_DIR, cer, find_cjk_font, peak_rss_mb, rss_mb, save_result, timer

SYNTH = [
    ("clean", "智能文档管理系统设计与实现\n第三章 检索模块\n2024年度财务报告摘要", 40, 0, 0),
    ("small", "发票号码 12345678 开票日期 2024年3月5日\n购买方名称：某某科技有限公司 金额 980.00 元", 18, 0, 0),
    ("lowq", "会议纪要：讨论图文跨模态检索与结果融合方案\n参会人员：张三 李四 王五", 26, 1.2, 70),
]


def make_samples() -> list[tuple[Path, str]]:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    font_path = find_cjk_font()
    if font_path is None:
        print("[警告] 未找到中文字体，跳过生成测试图；请用 --images 提供图片。")
        return []
    out = []
    for name, text, size, blur, gray in SYNTH:
        font = ImageFont.truetype(font_path, size)
        lines = text.split("\n")
        w = max(int(font.getlength(l)) for l in lines) + 60
        h = (size + 16) * len(lines) + 60
        img = Image.new("RGB", (w, h), (255, 255, 255))
        d = ImageDraw.Draw(img)
        color = (gray, gray, gray)
        for i, l in enumerate(lines):
            d.text((30, 30 + i * (size + 16)), l, font=font, fill=color)
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(blur))
        p = SAMPLES_DIR / f"ocr_{name}.png"
        img.save(p)
        out.append((p, text))
    return out


class OCRAdapter:
    """兼容 PaddleOCR 2.x（.ocr）与 3.x（.predict）两种 API。"""

    def __init__(self, mobile: bool):
        from paddleocr import PaddleOCR

        self.api = None
        self.init_note = ""
        if hasattr(PaddleOCR, "predict"):
            kwargs = dict(use_doc_orientation_classify=False, use_doc_unwarping=False,
                          use_textline_orientation=False)
            if mobile:
                kwargs.update(text_detection_model_name="PP-OCRv5_mobile_det",
                              text_recognition_model_name="PP-OCRv5_mobile_rec")
            try:
                self.engine = PaddleOCR(**kwargs)
                self.init_note = "3.x predict API" + (" + mobile 模型" if mobile else " + 默认模型")
            except Exception as e:  # 模型名在不同版本可能不同，退回默认配置
                self.engine = PaddleOCR(lang="ch")
                self.init_note = f"3.x predict API，指定模型失败已回退默认（{str(e)[:120]}）"
            self.api = "predict"
        else:
            self.engine = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
            self.api = "ocr"
            self.init_note = "2.x ocr API"

    def run(self, path: Path) -> tuple[str, list[float]]:
        if self.api == "predict":
            res = self.engine.predict(str(path))
            texts, scores = [], []
            for r in res:
                data = r.json if hasattr(r, "json") else dict(r)
                data = data.get("res", data)
                texts += list(data.get("rec_texts", []))
                scores += [float(s) for s in data.get("rec_scores", [])]
            return "\n".join(texts), scores
        res = self.engine.ocr(str(path), cls=False)
        lines = (res[0] or []) if res else []
        return "\n".join(l[1][0] for l in lines), [float(l[1][1]) for l in lines]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, help="额外测试图片所在文件夹（png/jpg）")
    ap.add_argument("--mobile", action="store_true", help="优先使用轻量 mobile 模型（3.x）")
    ap.add_argument("--repeat", type=int, default=3, help="每张图重复识别次数")
    ap.add_argument("--hold", action="store_true", help="加载模型后保持运行，供并发内存测试")
    args = ap.parse_args()

    result: dict = {"errors": [], "mobile_requested": args.mobile}
    try:
        import paddle
        import paddleocr
        result["paddle_version"] = paddle.__version__
        result["paddleocr_version"] = getattr(paddleocr, "__version__", "unknown")
        result["paddle_device"] = paddle.device.get_device()
    except Exception as e:
        result["errors"].append(f"导入 paddle/paddleocr 失败：{e}")
        print(result["errors"][-1])
        save_result("02_ocr", result)
        return

    result["rss_before_load_mb"] = rss_mb()
    with timer(result, "model_load_s"):
        ocr = OCRAdapter(args.mobile)
    result["api"] = ocr.init_note
    result["rss_after_load_mb"] = rss_mb()
    print(f"paddle {result['paddle_version']} / paddleocr {result['paddleocr_version']} / {result['paddle_device']}")
    print(f"{ocr.init_note}，模型加载 {result['model_load_s']} s，内存 {result['rss_after_load_mb']} MB")

    if args.hold:
        print("\n[--hold] 模型已加载，进程保持运行。另开终端运行 04_mem_snapshot.py，完成后按 Ctrl+C 结束。")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    cases: list[tuple[Path, str | None]] = list(make_samples())
    if args.images:
        for p in sorted(args.images.expanduser().iterdir()):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                gt = p.with_suffix(".txt")
                cases.append((p, gt.read_text(encoding="utf-8") if gt.exists() else None))

    # 预热一次，避免把首次推理的初始化开销算进单图耗时
    if cases:
        ocr.run(cases[0][0])

    per_image = []
    for path, gt in cases:
        times = []
        text = ""
        for _ in range(args.repeat):
            t = time.perf_counter()
            text, scores = ocr.run(path)
            times.append(time.perf_counter() - t)
        item = {
            "file": path.name,
            "avg_s": round(sum(times) / len(times), 4),
            "min_s": round(min(times), 4),
            "max_s": round(max(times), 4),
            "mean_conf": round(sum(scores) / len(scores), 4) if scores else None,
            "text": text,
        }
        if gt is not None:
            item["cer"] = cer(gt, text)
        per_image.append(item)
        print(f"\n[{path.name}] 平均 {item['avg_s']} s，CER={item.get('cer', '无标准文本')}")
        print("  识别结果：" + text.replace("\n", " | "))

    result["per_image"] = per_image
    if per_image:
        result["avg_s_per_image"] = round(sum(i["avg_s"] for i in per_image) / len(per_image), 4)
        cers = [i["cer"] for i in per_image if "cer" in i]
        result["avg_cer"] = round(sum(cers) / len(cers), 4) if cers else None
    result["peak_rss_mb"] = peak_rss_mb()
    print(f"\n平均每图 {result.get('avg_s_per_image')} s，平均 CER {result.get('avg_cer')}，峰值内存 {result['peak_rss_mb']} MB")
    save_result("02_ocr", result)


if __name__ == "__main__":
    main()
