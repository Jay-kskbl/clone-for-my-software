"""父进程一消失，本进程（Worker 的子进程）就立即退出（T24ab，D53）。

为什么需要：multiprocessing 的 daemon 子进程只在父进程**正常退出**时才会被结束。父进程被强制
结束（kill -9、任务管理器、Stop-Process -Force、内存不足被系统杀掉）时，子进程会照常跑下去，
而超时、续租都由父进程负责，这时已经没人管它了。租约到期后任务会被别的 Worker 重新领取，
两边就可能同时写同一个文档（GLOBAL §3.3）。
"""

import multiprocessing
import os
import threading
from multiprocessing.connection import wait

# 没有人会读到这个退出码（父进程已经不在了），只要不是 0
_EXIT_CODE = 1


def exit_when_parent_dies() -> None:
    """启动一个后台线程盯着父进程。在子进程入口的开头调用；在主进程里调用什么也不做。"""
    parent = multiprocessing.parent_process()
    if parent is None:
        return
    threading.Thread(
        target=_watch, args=(parent.sentinel,), name="parent-watch", daemon=True
    ).start()


def _watch(sentinel: int) -> None:
    wait([sentinel])
    # 用 os._exit 而不是 sys.exit：后者在线程里只结束这个线程；主线程可能正卡在解析库里。
    # 未提交的数据库事务随连接断开回滚；已写的部分由重新领取的任务按确定性 ID 覆盖。
    os._exit(_EXIT_CODE)
