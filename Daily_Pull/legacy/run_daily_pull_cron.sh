#!/usr/bin/env bash
#
# Prismax Daily Work - Cron 入口脚本
# 由 crontab 每周一至周五 9:30（建议）调用；加载 daily_pull_env.sh 后执行
# run_daily_pull_once.sh（内含 9:25–9:45 时间窗与工作日判断）。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAILY_PULL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${DAILY_PULL_DIR}/daily_pull_env.sh"
if [[ -f "${DAILY_PULL_DIR}/daily_pull_env.local.sh" ]]; then
    # shellcheck source=/dev/null
    source "${DAILY_PULL_DIR}/daily_pull_env.local.sh"
fi
exec "${SCRIPT_DIR}/run_daily_pull_once.sh"
