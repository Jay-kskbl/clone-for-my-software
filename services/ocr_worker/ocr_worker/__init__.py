"""M6 OCR Worker（ocr 环境）：只领取 ocr 任务，把扫描页和图片里的文字识别出来，
写入 ocr_results 和 source_type=ocr 的片段，并写进 chunks 索引（GLOBAL §3.4、DEVPLAN T17）。

模块划分：
    config.py          配置（.env 与环境变量），启动时检查
    models.py          模型目录检查、模型名称与版本（含文件哈希）
    rendering.py       PDF 页 / 图片 → RGB 像素（PyMuPDF）
    engine.py          PaddleOCR 的封装（只在 ocr 环境里能导入 paddleocr）
    engine_process.py  常驻子进程：模型只加载一次；超时、崩溃时杀掉重开
    pipeline.py        一个任务的处理：版本比对 → 识别 → 写数据库 → 写索引
    store.py           对数据库的读写（psycopg，不依赖 backend）
    loop.py            主循环：领取、续租、回写结果、处理满 N 个后退出
"""
