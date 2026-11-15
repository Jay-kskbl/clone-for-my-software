"""M7：把一段过长的文本按字符窗口拆开，相邻两段之间留出重叠。

长度按字符数（Python 的 len）计算：中文一个字算一个，英文一个字母算一个。
"""

# 断开位置的优先级：先找换行，再找句末标点，最后找空白和逗号。
# 不把英文句点单独当断点：“3.14”“v1.2” 里的点不是句末；英文句末的点后面跟着空格，空格会被找到。
_BREAK_GROUPS: tuple[frozenset[str], ...] = (
    frozenset("\n"),
    frozenset("。！？；!?;"),
    frozenset(" \t，,、"),
)


def _find_break(text: str, start: int, end: int, lookback: int) -> int:
    """在 (end - lookback, end] 内找一个合适的断开位置，返回断开后下一段的起点（即本段的终点）。

    找不到就在 end 处硬断开。
    """
    lower = max(start + 1, end - lookback)
    for group in _BREAK_GROUPS:
        for pos in range(end - 1, lower - 1, -1):
            if text[pos] in group:
                return pos + 1
    return end


def split_spans(text: str, *, max_chars: int, overlap_chars: int) -> list[tuple[int, int]]:
    """把 text 拆成若干 [start, end) 区间。

    保证：
    - 每个区间长度不超过 max_chars；
    - 第一个区间从 0 开始，最后一个区间到 len(text) 结束；
    - 后一个区间的起点落在前一个区间内部或恰好在其终点，且严格大于前一个的起点，
      所以依次取 text[前一个终点:本区间终点] 拼起来恰好还原原文（切分覆盖原文）。
    - 相邻区间的重叠不超过 overlap_chars。

    text 不超过 max_chars 时原样返回一个区间。
    """
    if max_chars < 1:
        raise ValueError("max_chars 必须大于 0")
    if not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap_chars 必须不小于 0 且小于 max_chars")

    length = len(text)
    if length <= max_chars:
        return [(0, length)]

    # 回头找断点的范围：窗口的后四分之一。再往前断，片段会太短
    lookback = max(1, max_chars // 4)
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        end = start + max_chars
        if end >= length:
            spans.append((start, length))
            return spans
        end = _find_break(text, start, end, lookback)
        spans.append((start, end))
        # 下一段从本段结尾往回 overlap_chars 处开始，但必须向前推进
        start = max(end - overlap_chars, start + 1)
