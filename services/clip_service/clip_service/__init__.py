"""M9 CLIP 模型服务（clip 环境）：常驻加载 Chinese-CLIP，把查询文本和图片编码成向量
（GLOBAL §3.4、§4.3，DEVPLAN T20）。只做推理，不训练、不微调。

模块划分：
    config.py     配置（.env 与环境变量），启动时检查
    core.py       模型信息、编码器接口、错误类型（不依赖 torch，接口层和测试都用它）
    models.py     权重文件检查、sha256、模型版本字符串（不依赖 torch）
    encoder.py    Chinese-CLIP 的封装（只在 clip 环境里能导入 torch、cn_clip、PIL）
    app.py        HTTP 接口：/health、/encode/text、/encode/image（不依赖 torch）
    __main__.py   入口：检查配置和模型 → 加载模型 → 启动 uvicorn
"""
