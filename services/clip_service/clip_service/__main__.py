"""CLIP 模型服务入口（clip 环境）。在 services/clip_service/ 目录下运行：

    ../../env_check/.venv-clip/bin/python -m clip_service

启动顺序：读配置 → 检查权重文件（缺失即退出，不下载）→ 加载模型并自检 → 开始监听。
模型只在这里加载一次（GLOBAL §4.3）；监听开始时模型一定已经可用。

退出码：1 配置、权重文件或模型有问题；被 Ctrl+C 或 SIGTERM 停止时，退出码由 uvicorn 按信号给出。
"""

import logging
import sys

from clip_service.config import ConfigError, load_settings
from clip_service.models import check_model_file

logger = logging.getLogger("clip_service")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings()
        sha256 = check_model_file(settings.clip_model_path, settings.clip_model_sha256)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    # 配置和文件都没问题之后才导入 torch：缺文件时能在 1 秒内报错退出
    try:
        import uvicorn

        from clip_service.app import create_app
        from clip_service.encoder import load_encoder
    except ImportError as exc:
        print(
            f"CLIP 服务无法启动：缺少依赖（{exc.name}）。请在 clip 环境里运行，"
            "依赖见 services/clip_service/requirements.txt",
            file=sys.stderr,
        )
        return 1

    try:
        encoder = load_encoder(
            settings.clip_model_path,
            model_name=settings.clip_model_name,
            device=settings.clip_device,
            sha256=sha256,
            max_image_pixels=settings.clip_max_image_pixels,
        )
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    info = encoder.info
    logger.info(
        "CLIP 模型已加载：%s，%s，维度 %d，设备 %s",
        info.model_name,
        info.model_version,
        info.dim,
        info.device,
    )

    uvicorn.run(
        create_app(encoder, settings),
        host=settings.clip_host,
        port=settings.clip_port,
        log_level="info",
        # 访问日志只有方法、路径和状态码，不含请求体
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
