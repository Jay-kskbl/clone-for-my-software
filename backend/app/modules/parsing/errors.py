"""M5 解析错误。"""


class ParseError(Exception):
    """文件无法解析。message 会作为任务的失败原因保存并展示给用户，不得包含服务器路径。

    retryable=False 表示重试也不会成功（文件本身损坏、加密等），
    任务处理函数据此直接把任务标记为 failed，不浪费重试次数。
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
