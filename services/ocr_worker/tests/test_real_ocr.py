"""T17 🧪：用真实的 PP-OCRv5 mobile 模型识别现场生成的测试图。

只在 ocr 环境里运行，用标准库 unittest（ocr 环境没有装 pytest）。在 services/ocr_worker/ 下：

    ../../env_check/.venv-ocr/bin/python -m unittest tests.test_real_ocr -v

在 main 环境里（没有 paddleocr）整个文件被跳过。模型目录缺失时同样跳过并说明原因。
"""

import functools
import importlib.util
import tempfile
import unittest
import uuid
from pathlib import Path

import pymupdf

from ocr_worker.config import load_settings
from ocr_worker.engine_process import EngineProcess, Job
from ocr_worker.models import check_models

HAS_PADDLE = importlib.util.find_spec("paddleocr") is not None
TEXT_1 = "智能文档管理系统"
TEXT_2 = "OCR 2026"


def _settings():
    return load_settings(
        environ={"DATABASE_URL": "postgresql://unused/x", "OPENSEARCH_URL": "http://unused:1"}
    )


def _models_present() -> bool:
    settings = _settings()
    return settings.ocr_det_model_dir.is_dir() and settings.ocr_rec_model_dir.is_dir()


def _make_scanned_pdf(path: Path) -> None:
    """一页“扫描件”：文字先画成图片再贴进 PDF，没有文本层，只有 OCR 才读得出来。"""
    text_doc = pymupdf.open()
    page = text_doc.new_page(width=400, height=160)
    page.insert_text((30, 60), TEXT_1, fontname="china-s", fontsize=28)
    page.insert_text((30, 120), TEXT_2, fontname="helv", fontsize=28)
    picture = page.get_pixmap(dpi=150)
    text_doc.close()

    scan = pymupdf.open()
    scan_page = scan.new_page(width=400, height=160)
    scan_page.insert_image(scan_page.rect, pixmap=picture)
    assert scan_page.get_text().strip() == ""
    scan.save(path)
    scan.close()


@unittest.skipUnless(HAS_PADDLE, "当前环境没有 paddleocr，真实识别测试只在 ocr 环境里运行")
@unittest.skipUnless(HAS_PADDLE and _models_present(), "模型目录不存在（见 OCR_DET_MODEL_DIR）")
class RealOcrTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from ocr_worker.engine import make_paddle_engine

        settings = _settings()
        cls.model = check_models(settings.ocr_det_model_dir, settings.ocr_rec_model_dir)
        cls.engine = EngineProcess(
            functools.partial(
                make_paddle_engine, str(cls.model.det_dir), str(cls.model.rec_dir), "cpu"
            ),
            load_timeout_seconds=300,
        )
        cls.engine.start()
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.close()
        cls.tmp.cleanup()

    def recognize(self, path: Path, locator: dict) -> list[str]:
        result = self.engine.run(
            Job(path=str(path), locator=locator, dpi=200, max_pixels=10**8),
            timeout_seconds=300,
            tick_seconds=1,
        )
        self.assertTrue(result.ok, result.error)
        for line in result.lines:
            self.assertGreaterEqual(line.confidence, 0.0)
            self.assertLessEqual(line.confidence, 1.0)
            self.assertEqual(len(line.bbox), 4)
        return [line.text for line in result.lines]

    def test_scanned_pdf_page_is_recognized(self) -> None:
        path = Path(self.tmp.name) / "scan.pdf"
        _make_scanned_pdf(path)

        texts = self.recognize(path, {"type": "pdf_page", "page": 1})

        joined = "".join("".join(texts).split())
        self.assertIn("".join(TEXT_1.split()), joined)
        self.assertIn("2026", joined)

    def test_standalone_image_is_recognized(self) -> None:
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=100)
        page.insert_text((30, 60), TEXT_1, fontname="china-s", fontsize=28)
        path = Path(self.tmp.name) / "photo.png"
        path.write_bytes(page.get_pixmap(dpi=150).tobytes("png"))
        doc.close()

        texts = self.recognize(path, {"type": "image", "image_id": str(uuid.uuid4())})

        self.assertIn(TEXT_1, "".join("".join(texts).split()))

    def test_blank_image_gives_no_text(self) -> None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 100), False)
        pix.clear_with(255)
        path = Path(self.tmp.name) / "blank.png"
        path.write_bytes(pix.tobytes("png"))

        self.assertEqual(self.recognize(path, {"type": "image", "image_id": str(uuid.uuid4())}), [])

    def test_model_version_records_the_library_and_weights(self) -> None:
        version = self.model.model_version(self.engine.library_version or "")

        self.assertTrue(version.startswith("paddleocr-3."))
        self.assertIn(self.model.det_sha256[:8], version)


if __name__ == "__main__":
    unittest.main()
