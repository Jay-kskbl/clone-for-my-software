"""CLIP 服务的接口测试在 main 环境里运行（那里有 pytest、httpx），编码器用假的。

真正加载 Chinese-CLIP 的测试在 test_real_clip.py，只在 clip 环境里运行。
"""
