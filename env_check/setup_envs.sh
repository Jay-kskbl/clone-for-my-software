#!/usr/bin/env bash
# 创建三个相互隔离的虚拟环境（GLOBAL.md §3.4）：
#   .venv-main  主环境：只装 psutil，跑 00/01/04/05
#   .venv-ocr   OCR 环境：PaddlePaddle + PaddleOCR，跑 02
#   .venv-clip  CLIP 环境：PyTorch + Chinese-CLIP，跑 03
#
# 用法：
#   bash setup_envs.sh            # 三个都建
#   bash setup_envs.sh main ocr   # 只建指定的
#
# 建议用 Python 3.11（PaddlePaddle 与 PyTorch 都支持的版本）。可用 PY 环境变量指定解释器：
#   PY=python3.11 bash setup_envs.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results

PY="${PY:-}"
if [[ -z "$PY" ]]; then
  for c in python3.11 python3.12 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
echo "使用解释器：$PY ($($PY --version))"

TARGETS=("$@")
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(main ocr clip)

for t in "${TARGETS[@]}"; do
  venv=".venv-$t"
  req="requirements-$t.txt"
  echo
  echo "==== 创建 $venv（$req）===="
  "$PY" -m venv "$venv"
  "$venv/bin/python" -m pip install --upgrade pip
  "$venv/bin/pip" install -r "$req"
  # 冻结实际安装的版本：环境实测通过后，这份清单就是正式项目锁定依赖的起点
  "$venv/bin/pip" freeze > "results/freeze-$t.txt"
  echo "已记录实际版本：results/freeze-$t.txt"
done

echo
echo "完成。下一步见 README.md 的「运行顺序」。"
