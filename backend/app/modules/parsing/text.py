"""M5：各解析器共用的文本清理。"""


def clean_text(text: str) -> str:
    """去掉空字符（PostgreSQL 的 text 类型不能保存它）、每行末尾的空白和首尾空行。"""
    lines = [line.rstrip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(lines).strip()
