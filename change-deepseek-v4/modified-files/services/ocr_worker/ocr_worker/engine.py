"""PaddleOCR 的封装。只在 ocr 环境里使用（那里才装了 paddleocr 和 numpy）。

本模块在导入时不导入 paddleocr / numpy：别的模块可以放心地 import 它，
真正的导入发生在 PaddleEngine 创建时（在识别子进程里）。
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ocr_worker.rendering import RenderedImage

# 不让 PaddleX 去联网检查模型源（模型只从本地目录加载，GLOBAL §3.4）
OFFLINE_ENV = {"PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"}


@dataclass(frozen=True)
class RecognizedLine:
    text: str
    confidence: float
    # 四个顶点（左上、右上、右下、左下），像素坐标
    bbox: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]


class Engine(Protocol):
    """识别引擎的全部要求。测试用假实现替换，不需要 PaddleOCR。"""

    library_version: str

    def recognize(self, image: RenderedImage) -> list[RecognizedLine]: ...


def quad_from_points(points: Any) -> tuple[tuple[float, float], ...]:
    """把检测框整理成四个顶点。正好四个点时原样使用；否则取外接矩形。"""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) == 4:
        return tuple(pts)
    if not pts:
        return ((0.0, 0.0),) * 4
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    return ((left, top), (right, top), (right, bottom), (left, bottom))


class PaddleEngine:
    """PP-OCR 检测 + 识别。只用文本检测和文字识别两个模型：

    文档方向分类、文档矫正、文本行方向分类都关闭——它们需要另外的模型文件，
    开启后会去下载，而本项目只允许从配置的目录加载模型。
    """

    def __init__(self, *, det_dir: Path, rec_dir: Path, device: str) -> None:
        for key, value in OFFLINE_ENV.items():
            os.environ.setdefault(key, value)
        import paddleocr
        from paddleocr import PaddleOCR

        self.library_version = str(paddleocr.__version__)
        self._ocr = PaddleOCR(
            text_detection_model_name=det_dir.name,
            text_detection_model_dir=str(det_dir),
            text_recognition_model_name=rec_dir.name,
            text_recognition_model_dir=str(rec_dir),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # PaddlePaddle 3.3.1 在 Windows CPU 上启用 oneDNN 时会拒绝加载
            # PP-OCRv5 的 PIR 属性（NotImplementedError），关闭后推理正常。
            enable_mkldnn=os.name != "nt",
            device=device,
        )

    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        import numpy as np

        rgb = np.frombuffer(image.rgb, dtype=np.uint8).reshape(image.height, image.width, 3)
        # PaddleOCR 与 OpenCV 一样按 BGR 顺序理解数组
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        lines: list[RecognizedLine] = []
        for result in self._ocr.predict(bgr):
            # 与 env_check/02_check_ocr.py 实测过的取法一致
            data = result.json if hasattr(result, "json") else dict(result)
            data = data.get("res", data)
            # 只用 rec_* 三个列表：它们一一对应，且已按识别分数阈值过滤。
            # dt_polys 含被过滤掉的检测框，和 rec_texts 对不上，不能用
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            polys = data.get("rec_polys", [])
            for text, score, poly in zip(texts, scores, polys, strict=False):
                lines.append(
                    RecognizedLine(
                        text=str(text),
                        confidence=min(1.0, max(0.0, float(score))),
                        bbox=quad_from_points(poly),
                    )
                )
        return lines


def make_paddle_engine(det_dir: str, rec_dir: str, device: str) -> PaddleEngine:
    """识别子进程的入口用它创建引擎。参数都是字符串，便于跨进程传递。"""
    return PaddleEngine(det_dir=Path(det_dir), rec_dir=Path(rec_dir), device=device)
