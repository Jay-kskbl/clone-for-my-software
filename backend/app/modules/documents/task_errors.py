"""任务失败原因的对外文字（T24ba，docs/changes/T24ba.md）。

Worker 把异常写成“类型名: 异常文字”存进 processing_tasks.error
（worker/runner.py、ocr_worker/loop.py）。
项目自己的错误（ParseError 等）约定不含服务器路径和服务地址，可以给用户看；
没有预料到的异常（FileNotFoundError、SQLAlchemy 的 OperationalError 等）的文字里会带上
服务器路径、数据库主机名和端口、SQL 参数，不能原样返回（GLOBAL §7.2）。

所以只放行认得出来的写法，其余一律只给异常的类型名：新增的异常默认不外露，
漏登记的后果是说明不够详细，而不是泄露。数据库里仍是原文，管理员看到的也是原文。
"""

import re

# “类型名: 说明”。异常的 str() 可能是空的，也可能有多行
_TYPED = re.compile(r"([A-Za-z_][A-Za-z0-9_]*): ?(.*)", re.DOTALL)

# 说明可以完整给用户看的异常：类的文档里约定了 message 不含服务器路径和服务地址
_PUBLIC_TYPES = frozenset(
    {
        "ParseError",  # modules/parsing/errors.py
        "PipelineError",  # worker/handlers/errors.py
        "ClipUnavailable",  # modules/clip/client.py
        "ClipRejected",
        "OcrTaskError",  # services/ocr_worker/ocr_worker/pipeline.py
        "RenderError",  # services/ocr_worker/ocr_worker/rendering.py
    }
)

# 检索服务的应答原因里可能有节点名和内网地址（例如 remote_transport_exception 的
# “[node][172.18.0.2:9300][…]”），只保留到 HTTP 状态码为止
_TEXT_INDEX_TYPES = frozenset({"TextIndexError", "TextIndexUnavailable"})
_TEXT_INDEX_PUBLIC = re.compile(r"检索服务[一-鿿]+（(?:HTTP \d{3}|[A-Za-z_][A-Za-z0-9_]*)")

# 后面跟着内部异常的文字（可能含模型目录），只保留前半句
_OCR_LOAD_FAILED = "OCR 模型加载失败"

# 任务框架自己写的、没有类型名前缀的原因（runner.py、engine_process.py、loop.py、shared/tasks.py）
_FRAMEWORK_MESSAGES = (
    re.compile(r"(?:处理|识别)超时（超过 [\d.e+]+ 秒），已终止"),
    re.compile(r"(?:识别)?子进程异常退出（退出码 (?:-?\d+|None)）"),
    re.compile(r"加载 OCR 模型超时（超过 [\d.e+]+ 秒）"),
    re.compile(r"OCR 子进程启动时异常退出（退出码 (?:-?\d+|None)）"),
    re.compile(r"租约过期：Worker 可能已崩溃，或任务卡住未能续租"),
    re.compile(r"租约已丢失，停止处理"),
    re.compile(r"未知错误"),
)

INTERNAL = "系统内部错误"


def _framework_message(text: str) -> str | None:
    return text if any(p.fullmatch(text) for p in _FRAMEWORK_MESSAGES) else None


def public_task_error(error: str | None) -> str | None:
    """把数据库里的失败原因变成可以给普通用户看的文字。没有失败原因时返回 None。"""
    if error is None:
        return None
    typed = _TYPED.fullmatch(error)
    if typed is None:
        return _framework_message(error) or INTERNAL

    name, message = typed.groups()
    if name in _PUBLIC_TYPES and message:
        return message
    if name in _TEXT_INDEX_TYPES:
        public = _TEXT_INDEX_PUBLIC.match(message)
        return f"{public.group()}）" if public else "检索服务出错"
    if name == "EngineStartError":
        if message.startswith(_OCR_LOAD_FAILED):
            return _OCR_LOAD_FAILED
        return _framework_message(message) or _OCR_LOAD_FAILED
    if name == "MemoryError":
        return "处理时内存不足，已终止"
    return f"{INTERNAL}（{name}）"
