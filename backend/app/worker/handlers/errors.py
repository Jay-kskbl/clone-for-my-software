"""任务处理函数自己抛出的错误。"""


class PipelineError(Exception):
    """流水线里重试也不会成功的失败（原始文件不见了、文件类型不认识等）。

    Worker 看到 retryable=False 就直接把任务标记为 failed，不浪费重试次数。
    message 会作为任务的失败原因保存并展示给用户，不得包含服务器路径。
    """

    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
