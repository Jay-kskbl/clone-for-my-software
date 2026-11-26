"""T24ab：父进程看门狗。强制结束父进程的端到端测试在两个 Worker 各自的测试里。"""

import threading

from shared.parent_watch import exit_when_parent_dies


def test_does_nothing_in_the_main_process():
    before = threading.active_count()

    exit_when_parent_dies()

    # 主进程没有 multiprocessing 父进程：不启动线程，更不会把自己结束掉
    assert threading.active_count() == before
