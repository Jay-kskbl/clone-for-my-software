"""项目内的错误类型。"""


class ConfigError(Exception):
    """配置缺失或不合法。启动时抛出，让进程带着可读的错误信息退出。"""
