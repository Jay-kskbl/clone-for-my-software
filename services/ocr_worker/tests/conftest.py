"""OCR Worker 的测试在 main 环境里运行（那里有 pytest、PyMuPDF、psycopg）。

真正调用 PaddleOCR 的测试在 test_real_ocr.py，只在 ocr 环境里运行。
"""

import sys
from pathlib import Path

# fakes.py 要能被识别子进程（spawn）按模块名导入
sys.path.insert(0, str(Path(__file__).parent))
