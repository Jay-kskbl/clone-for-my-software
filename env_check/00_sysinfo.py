"""第 0 步：记录本机硬件与软件环境（论文"实验环境"一节的依据）。

运行：.venv-main/bin/python 00_sysinfo.py
"""
import shutil
import subprocess

from _common import save_result, system_info


def cmd_version(cmd: list[str]) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = (out.stdout + "\n" + out.stderr).strip().splitlines()
        # java -version 可能先输出 "Picked up JAVA_TOOL_OPTIONS..."，优先取含 version 的行
        return next((l for l in lines if "version" in l.lower() and "picked up" not in l.lower()),
                    lines[0] if lines else None)
    except Exception as e:  # 记录失败原因而不是吞掉
        return f"error: {e}"


def main():
    info = system_info()
    tools = {
        "docker": cmd_version(["docker", "--version"]),
        "docker_compose": cmd_version(["docker", "compose", "version"]),
        "java": cmd_version(["java", "-version"]),
        "node": cmd_version(["node", "--version"]),
        "psql": cmd_version(["psql", "--version"]),
        "git": cmd_version(["git", "--version"]),
    }
    info["tools"] = tools

    print("== 系统信息 ==")
    for k, v in info.items():
        if k != "tools":
            print(f"{k:20s} {v}")
    print("\n== 工具 ==")
    for k, v in tools.items():
        print(f"{k:20s} {v or '未安装'}")

    total = info.get("total_mem_gb")
    if total is not None and total < 16:
        print(f"\n[提示] 总内存 {total} GB < 16 GB：同时运行 OpenSearch + OCR + CLIP 可能吃紧，"
              "请务必完成 04_mem_snapshot.py 的并发实测。")
    save_result("00_sysinfo", info)


if __name__ == "__main__":
    main()
