"""M8 文本索引的错误。

两类错误分开，是为了让调用方区分“等一会儿再试可能就好了”和“再试也没用”：
任务处理函数抛出的异常带有 retryable 属性时，Worker 据此决定是否重试（见 worker/runner.py）。
检索接口（T15）遇到这两类错误都要明确报告检索服务故障，不能当成“没有结果”（GLOBAL §12）。
"""


class TextIndexError(Exception):
    """检索服务拒绝了请求：索引结构不匹配、请求格式错误等。重试也不会成功。

    message 可能展示给用户或写进任务的失败原因，不得包含服务地址。
    """

    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TextIndexUnavailable(TextIndexError):
    """检索服务连不上、超时或内部出错。稍后重试可能成功。"""

    retryable = True
