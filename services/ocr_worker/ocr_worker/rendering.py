"""把要识别的对象变成 RGB 像素：PDF 的某一页按固定分辨率渲染，图片直接解码。

只依赖 PyMuPDF，不依赖 numpy：这样不装 PaddleOCR 的环境里也能测试。
像素到 numpy 数组的转换在 engine.py 里做。
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf
from shared.contracts import ImageLocator, OcrLocator, PdfPageLocator


class RenderError(Exception):
    """对象无法渲染（文件损坏、页码不存在、尺寸超限）。重试也不会成功。"""

    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class RenderedImage:
    width: int
    height: int
    # 逐行排列的 RGB 像素，每个像素 3 字节，长度 = width × height × 3
    rgb: bytes


def _to_rgb(pix: pymupdf.Pixmap) -> pymupdf.Pixmap:
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)  # 去掉透明通道
    if pix.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)  # 灰度、CMYK 等一律转成 RGB
    return pix


def _check_size(width: int, height: int, max_pixels: int) -> None:
    if width < 1 or height < 1:
        raise RenderError("图片的宽或高为 0")
    if width * height > max_pixels:
        raise RenderError(f"图片尺寸为 {width}×{height}，像素数超过上限 {max_pixels}，拒绝识别")


def _render_pdf_page(path: Path, page_number: int, dpi: int, max_pixels: int) -> pymupdf.Pixmap:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 —— 库对损坏文件抛出的异常类型不固定
        raise RenderError(f"PDF 无法打开（{type(exc).__name__}）") from exc
    try:
        if not 1 <= page_number <= doc.page_count:
            raise RenderError(f"PDF 没有第 {page_number} 页（共 {doc.page_count} 页）")
        page = doc.load_page(page_number - 1)
        # 先按页面尺寸算出渲染后的像素数，超限就不渲染，免得先吃掉大量内存
        scale = dpi / 72
        _check_size(round(page.rect.width * scale), round(page.rect.height * scale), max_pixels)
        return page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    except RenderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"PDF 第 {page_number} 页无法渲染（{type(exc).__name__}）") from exc
    finally:
        doc.close()


def _decode_image(path: Path) -> pymupdf.Pixmap:
    try:
        return pymupdf.Pixmap(str(path))
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"图片无法解码（{type(exc).__name__}）") from exc


def render(path: Path, locator: OcrLocator, *, dpi: int, max_pixels: int) -> RenderedImage:
    """把 locator 指向的对象渲染成 RGB 像素。"""
    if isinstance(locator, PdfPageLocator):
        pix = _render_pdf_page(path, locator.page, dpi, max_pixels)
    elif isinstance(locator, ImageLocator):
        pix = _decode_image(path)
    else:  # pragma: no cover —— OcrLocator 只有这两种
        raise RenderError(f"不支持识别这种对象：{locator!r}")
    _check_size(pix.width, pix.height, max_pixels)
    pix = _to_rgb(pix)
    return RenderedImage(width=pix.width, height=pix.height, rgb=bytes(pix.samples))
