"""T20 🧪：用真实的 Chinese-CLIP 模型，经真实的 HTTP 服务测三项要求：
健康检查；同一输入向量稳定；超大图片和损坏图片的处理。

只在 clip 环境里运行，用标准库 unittest 和 urllib（clip 环境没有装 pytest、httpx）。
在 services/clip_service/ 下：

    ../../env_check/.venv-clip/bin/python -m unittest tests.test_real_clip -v

在 main 环境里（没有 torch）整个文件被跳过。权重文件缺失时同样跳过并说明原因。
测试图片都是现场生成的。
"""

import importlib.util
import io
import json
import math
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request

from clip_service.config import load_settings

HAS_TORCH = all(importlib.util.find_spec(name) is not None for name in ("torch", "cn_clip", "PIL"))
MAX_PIXELS = 1_000_000
MAX_BYTES = 2_000_000


def _settings():
    return load_settings(
        env_file=None,
        environ={
            "CLIP_DEVICE": "cpu",
            "CLIP_MAX_IMAGE_PIXELS": str(MAX_PIXELS),
            "CLIP_MAX_IMAGE_BYTES": str(MAX_BYTES),
        },
    )


def _image_bytes(color, size=(96, 96), fmt="PNG", mode="RGB", **save_args) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, fmt, **save_args)
    return buffer.getvalue()


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@unittest.skipUnless(HAS_TORCH, "不在 clip 环境里（没有 torch / cn_clip / PIL）")
@unittest.skipUnless(_settings().clip_model_path.is_file(), "models/clip/ 下没有权重文件")
class RealClipServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn

        from clip_service.app import create_app
        from clip_service.encoder import load_encoder
        from clip_service.models import check_model_file

        settings = _settings()
        cls.sha256 = check_model_file(settings.clip_model_path)
        cls.encoder = load_encoder(
            settings.clip_model_path,
            model_name=settings.clip_model_name,
            device=settings.clip_device,
            sha256=cls.sha256,
            max_image_pixels=settings.clip_max_image_pixels,
        )
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.server = uvicorn.Server(
            uvicorn.Config(
                create_app(cls.encoder, settings), host="127.0.0.1", port=port, log_level="warning"
            )
        )
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 15
        while not cls.server.started:
            if time.monotonic() > deadline or not cls.thread.is_alive():
                raise RuntimeError("测试用的 CLIP 服务没有启动起来")
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)

    # ---- 小工具 ----

    def _request(self, method: str, path: str, body: bytes | None = None, content_type=None):
        request = urllib.request.Request(self.base + path, data=body, method=method)
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _text(self, texts):
        status, body = self._request(
            "POST", "/encode/text", json.dumps({"texts": texts}).encode(), "application/json"
        )
        self.assertEqual(status, 200, body)
        return body

    def _image(self, data: bytes):
        return self._request("POST", "/encode/image", data, "application/octet-stream")

    def _image_vector(self, data: bytes):
        status, body = self._image(data)
        self.assertEqual(status, 200, body)
        return body["vector"]

    def _assert_error(self, result, status: int, code: str):
        self.assertEqual(result[0], status, result[1])
        self.assertEqual(result[1]["error"]["code"], code)

    # ---- 🧪 健康检查 ----

    def test_health_reports_the_loaded_model(self):
        status, body = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["model_name"], "ViT-B-16")
        self.assertEqual(body["dim"], 512)
        self.assertEqual(body["device"], "cpu")
        # 版本里带权重文件哈希的前 12 位（GLOBAL §3.4：记录模型文件的 hash）
        self.assertTrue(body["model_version"].startswith("cn_clip-"))
        self.assertTrue(body["model_version"].endswith(self.sha256[:12]))
        self.assertLessEqual(len(body["model_version"]), 64)

    # ---- 🧪 同一输入向量稳定 ----

    def test_same_text_gives_identical_vectors(self):
        first = self._text(["会议室里的白板照片"])
        second = self._text(["会议室里的白板照片"])
        self.assertEqual(first["vectors"], second["vectors"])
        self.assertEqual(first["dim"], 512)
        self.assertEqual(len(first["vectors"][0]), 512)
        self.assertEqual(first["model_version"], second["model_version"])

    def test_text_vector_does_not_depend_on_the_rest_of_the_batch(self):
        """查询单独编码和夹在一批里编码，结果应当一样（允许浮点误差）。"""
        alone = self._text(["一只橘色的猫"])["vectors"][0]
        batched = self._text(["合同扫描件", "一只橘色的猫", "红色"])["vectors"][1]
        self.assertGreater(_dot(alone, batched), 0.9999)

    def test_same_image_gives_identical_vectors(self):
        data = _image_bytes((200, 40, 40))
        self.assertEqual(self._image_vector(data), self._image_vector(data))

    def test_vectors_are_unit_length_and_finite(self):
        vectors = self._text(["红色", "a", "很长的查询" * 100])["vectors"]
        vectors.append(self._image_vector(_image_bytes((10, 200, 10), fmt="JPEG")))
        for vector in vectors:
            self.assertEqual(len(vector), 512)
            self.assertTrue(all(math.isfinite(x) for x in vector))
            self.assertAlmostEqual(_dot(vector, vector), 1.0, places=4)

    def test_text_and_image_vectors_are_in_the_same_space(self):
        """只验证链路：红色图片对“红色”的相似度高于蓝色图片。不是检索效果数据。"""
        red_text, blue_text = self._text(["一张纯红色的图片", "一张纯蓝色的图片"])["vectors"]
        red = self._image_vector(_image_bytes((220, 30, 30)))
        blue = self._image_vector(_image_bytes((30, 60, 220)))
        self.assertGreater(_dot(red_text, red), _dot(red_text, blue))
        self.assertGreater(_dot(blue_text, blue), _dot(blue_text, red))

    def test_other_image_modes_are_accepted(self):
        for data in (
            _image_bytes((10, 20, 30, 128), mode="RGBA"),
            _image_bytes(128, mode="L"),
            _image_bytes(3, mode="P"),
            _image_bytes((0, 0, 0, 0), mode="CMYK", fmt="JPEG"),
            _image_bytes((1, 2, 3), size=(1, 1)),
            _image_bytes((1, 2, 3), size=(1000, 3)),
        ):
            self.assertEqual(len(self._image_vector(data)), 512)

    def test_exif_orientation_is_applied(self):
        """带 EXIF 方向标记的照片，按摆正后的画面编码（与用户在浏览器里看到的一致）。"""
        from PIL import Image

        base = Image.new("RGB", (120, 80), (220, 30, 30))
        base.paste((30, 60, 220), (60, 0, 120, 80))  # 左红右蓝
        exif = Image.Exif()
        exif[0x0112] = 6  # 显示时需要顺时针转 90 度
        tagged, upright, plain = io.BytesIO(), io.BytesIO(), io.BytesIO()
        base.save(tagged, "PNG", exif=exif)
        base.transpose(Image.Transpose.ROTATE_270).save(upright, "PNG")
        base.save(plain, "PNG")
        tagged_vector = self._image_vector(tagged.getvalue())
        self.assertGreater(_dot(tagged_vector, self._image_vector(upright.getvalue())), 0.9999)
        self.assertLess(_dot(tagged_vector, self._image_vector(plain.getvalue())), 0.9999)

    # ---- 🧪 超大图片 ----

    def test_image_over_pixel_limit_is_rejected_before_decoding(self):
        # 纯色大图压缩后只有几 KB，字节数远低于上限，只能靠像素数拦住
        data = _image_bytes((255, 255, 255), size=(2000, 1000))
        self.assertLess(len(data), MAX_BYTES)
        self._assert_error(self._image(data), 413, "IMAGE_TOO_LARGE")

    def test_image_at_pixel_limit_is_accepted(self):
        data = _image_bytes((255, 255, 255), size=(1000, 1000))
        self.assertEqual(len(self._image_vector(data)), 512)

    def test_pixel_bomb_beyond_pillow_own_limit_is_rejected(self):
        # 2 亿像素：超过 Pillow 自己的硬上限，打开时就报错，同样要给 413 而不是 500
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("1", (20000, 10000), 0).save(buffer, "PNG")
        data = buffer.getvalue()
        self.assertLess(len(data), MAX_BYTES)
        self._assert_error(self._image(data), 413, "IMAGE_TOO_LARGE")

    def test_body_over_byte_limit_is_rejected(self):
        self._assert_error(
            self._image(b"\x89PNG\r\n\x1a\n" + b"\0" * MAX_BYTES), 413, "IMAGE_TOO_LARGE"
        )

    # ---- 🧪 损坏图片 ----

    def test_corrupt_and_unsupported_images_are_rejected(self):
        good = _image_bytes((5, 5, 5), size=(300, 300))
        jpeg = _image_bytes((90, 90, 90), size=(300, 300), fmt="JPEG")
        cases = {
            "不是图片": b"this is not an image at all",
            "空请求体": b"",
            "只有 PNG 文件头": good[:8],
            "PNG 截断": good[: len(good) // 2],
            "JPEG 截断": jpeg[: len(jpeg) // 3],
            "PNG 数据段被改坏": good[:40] + bytes(len(good) - 80) + good[-40:],
            "GIF（不支持的格式）": _image_bytes(1, mode="P", fmt="GIF"),
            "BMP（不支持的格式）": _image_bytes((1, 2, 3), fmt="BMP"),
            "PDF": b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n",
        }
        for name, data in cases.items():
            with self.subTest(name):
                self._assert_error(self._image(data), 422, "INVALID_IMAGE")

    def test_service_keeps_working_after_bad_requests(self):
        self._image(b"garbage")
        self._image(_image_bytes((255, 255, 255), size=(2000, 1000)))
        status, _ = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(len(self._image_vector(_image_bytes((1, 2, 3)))), 512)

    # ---- 文本输入 ----

    def test_bad_text_requests_are_rejected(self):
        for payload in (
            {"texts": []},
            {"texts": [" "]},
            {"texts": ["x" * 1001]},
            {"texts": ["a"] * 33},
        ):
            with self.subTest(payload=str(payload)[:40]):
                result = self._request(
                    "POST", "/encode/text", json.dumps(payload).encode(), "application/json"
                )
                self._assert_error(result, 422, "VALIDATION_ERROR")


@unittest.skipUnless(HAS_TORCH, "不在 clip 环境里（没有 torch / cn_clip / PIL）")
class LoadFailureTest(unittest.TestCase):
    """模型有问题时启动失败，而不是带着坏模型运行或去下载。"""

    def _load(self, path, **overrides):
        from clip_service.encoder import load_encoder

        args = {
            "model_name": "ViT-B-16",
            "device": "cpu",
            "sha256": "0" * 64,
            "max_image_pixels": 100,
        }
        args.update(overrides)
        return load_encoder(path, **args)

    def test_garbage_weight_file_is_a_config_error(self):
        import tempfile
        from pathlib import Path

        from clip_service.config import ConfigError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.pt"
            path.write_bytes(b"definitely not a checkpoint")
            with self.assertRaises(ConfigError):
                self._load(path)

    def test_unknown_model_name_is_a_config_error(self):
        from clip_service.config import ConfigError

        with self.assertRaises(ConfigError):
            self._load(_settings().clip_model_path, model_name="ViT-X-99")


if __name__ == "__main__":
    unittest.main()
