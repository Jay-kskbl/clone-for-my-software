"""测试用的假识别引擎。必须是模块顶层的函数和类：识别子进程用 spawn 启动，要按名字导入它们。"""

import os
import time

from ocr_worker.engine import RecognizedLine
from ocr_worker.rendering import RenderedImage

BOX = ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))


class EchoEngine:
    """按图片尺寸“识别”出一行固定的文字，用来确认渲染结果确实传到了引擎。"""

    library_version = "fake-1.0"

    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        assert len(image.rgb) == image.width * image.height * 3
        return [
            RecognizedLine(text=f"尺寸 {image.width}x{image.height}", confidence=0.9, bbox=BOX),
            RecognizedLine(text="第二行文字", confidence=0.3, bbox=BOX),
        ]


class SlowEngine(EchoEngine):
    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        time.sleep(30)
        return []


class CrashingEngine(EchoEngine):
    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        os._exit(3)  # 模拟解释器崩溃：不报告任何结果就退出


class RaisingEngine(EchoEngine):
    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        raise RuntimeError("识别库内部错误")


class CtrlCEngine(EchoEngine):
    """识别途中收到 Ctrl-C（在终端里按下时信号也会发到识别子进程）。子进程应当忽略它。"""

    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        import signal

        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.2)
        return super().recognize(image)


class HeartbeatEngine(EchoEngine):
    """识别时每 0.05 秒写一个字节，最多 60 秒：文件停止变长就说明子进程已经不在了。"""

    def __init__(self, path: str) -> None:
        self._path = path

    def recognize(self, image: RenderedImage) -> list[RecognizedLine]:
        with open(self._path, "ab", buffering=0) as f:
            for _ in range(1200):
                f.write(b".")
                time.sleep(0.05)
        return []


def heartbeat_engine(path: str) -> HeartbeatEngine:
    return HeartbeatEngine(path)


def echo_engine() -> EchoEngine:
    return EchoEngine()


def ctrl_c_engine() -> CtrlCEngine:
    return CtrlCEngine()


def slow_engine() -> SlowEngine:
    return SlowEngine()


def crashing_engine() -> CrashingEngine:
    return CrashingEngine()


def raising_engine() -> RaisingEngine:
    return RaisingEngine()


def broken_engine() -> EchoEngine:
    raise FileNotFoundError("模型文件缺失")


def slow_loading_engine() -> EchoEngine:
    time.sleep(30)
    return EchoEngine()
