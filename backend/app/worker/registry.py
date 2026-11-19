"""通用 Worker（main 环境）能处理的任务类型 → 处理函数。

Worker 只领取这里登记了的类型，所以 ocr 任务不会被通用 Worker 误领
（它由 ocr 环境的 OCR Worker 负责）。embed 任务（T21）由通用 Worker 处理：
编码在 CLIP 服务进程里做，这里只发 HTTP 请求，不需要深度学习框架。

处理函数的要求：
- 是模块顶层的函数（子进程按名字导入它）；
- 幂等：同一个任务执行两次，结果与执行一次相同（GLOBAL §3.3）。写入用确定性 ID 覆盖，不追加。
"""

from shared.tasks import TASK_CLEANUP, TASK_EMBED, TASK_PARSE

from app.worker.handlers import handle_cleanup, handle_embed, handle_parse
from app.worker.runner import Handler

HANDLERS: dict[str, Handler] = {
    TASK_PARSE: handle_parse,
    TASK_CLEANUP: handle_cleanup,
    TASK_EMBED: handle_embed,
}
