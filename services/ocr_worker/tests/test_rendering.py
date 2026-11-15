"""T17：PDF 页与图片的渲染。"""

import uuid

import pymupdf
import pytest
from shared.contracts import ImageLocator, PdfPageLocator

from ocr_worker.rendering import RenderError, render

IMAGE_ID = str(uuid.UUID("11111111-2222-4333-8444-555555555555"))


def pdf_file(tmp_path, pages: int = 2):
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=200, height=100)
    path = tmp_path / "scan.pdf"
    doc.save(path)
    doc.close()
    return path


def image_file(tmp_path, *, alpha: bool = False, gray: bool = False, fmt: str = "png"):
    space = pymupdf.csGRAY if gray else pymupdf.csRGB
    pix = pymupdf.Pixmap(space, pymupdf.IRect(0, 0, 40, 20), alpha)
    pix.clear_with(128)
    path = tmp_path / f"img.{fmt}"
    path.write_bytes(pix.tobytes(fmt))
    return path


def test_pdf_page_is_rendered_at_the_requested_dpi(tmp_path):
    image = render(pdf_file(tmp_path), PdfPageLocator(page=2), dpi=144, max_pixels=10**8)

    # 200×100 点，144 dpi = 2 倍
    assert (image.width, image.height) == (400, 200)
    assert len(image.rgb) == 400 * 200 * 3


@pytest.mark.parametrize("kwargs", [{}, {"alpha": True}, {"gray": True}, {"fmt": "jpeg"}])
def test_images_become_plain_rgb(tmp_path, kwargs):
    image = render(
        image_file(tmp_path, **kwargs), ImageLocator(image_id=IMAGE_ID), dpi=200, max_pixels=10**8
    )

    assert (image.width, image.height) == (40, 20)
    assert len(image.rgb) == 40 * 20 * 3


def test_missing_page_is_a_non_retryable_error(tmp_path):
    with pytest.raises(RenderError, match="没有第 3 页") as excinfo:
        render(pdf_file(tmp_path), PdfPageLocator(page=3), dpi=72, max_pixels=10**8)

    assert excinfo.value.retryable is False


def test_oversized_page_is_rejected_before_rendering(tmp_path):
    with pytest.raises(RenderError, match="像素数超过上限"):
        render(pdf_file(tmp_path), PdfPageLocator(page=1), dpi=600, max_pixels=100_000)


def test_oversized_image_is_rejected(tmp_path):
    with pytest.raises(RenderError, match="像素数超过上限"):
        render(image_file(tmp_path), ImageLocator(image_id=IMAGE_ID), dpi=72, max_pixels=100)


@pytest.mark.parametrize("content", [b"%PDF-1.7 broken", b"not an image"])
def test_broken_files_are_render_errors(tmp_path, content):
    path = tmp_path / "broken"
    path.write_bytes(content)
    locator = (
        PdfPageLocator(page=1) if content.startswith(b"%PDF") else ImageLocator(image_id=IMAGE_ID)
    )

    with pytest.raises(RenderError):
        render(path, locator, dpi=72, max_pixels=10**8)
