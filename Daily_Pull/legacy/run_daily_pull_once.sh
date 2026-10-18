#!/usr/bin/env bash
#
# Daily Work：工作日 9:25–9:45 窗口内每日最多执行一次。
# 供 launchd 使用：周一至周五 9:30 触发 + RunAtLoad 在同窗口内补跑。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAILY_PULL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATE_FILE="${SCRIPT_DIR}/.last_run_date"
ENV_FILE="${DAILY_PULL_DIR}/daily_pull_env.sh"
ENV_LOCAL="${DAILY_PULL_DIR}/daily_pull_env.local.sh"
PYTHON_SCRIPT="${SCRIPT_DIR}/daily_work_pipeline.py"
LOG_FILE="${SCRIPT_DIR}/daily_pull.log"
PAUSE_FROM_FILE="${SCRIPT_DIR}/.daily_work_pause_from"

TODAY=$(date +%Y-%m-%d)

# 从某天起暂停生成 Daily_Work_Reports：
# - 方式 1：写文件 .daily_work_pause_from，内容为 YYYY-MM-DD
# - 方式 2：设置环境变量 DAILY_WORK_PAUSE_FROM=YYYY-MM-DD
# 若 TODAY >= PAUSE_FROM 则仅禁用“写报告”，但仍执行：拉取 git + 发送邮件
PAUSE_FROM="${DAILY_WORK_PAUSE_FROM:-}"
if [[ -z "$PAUSE_FROM" ]] && [[ -f "$PAUSE_FROM_FILE" ]]; then
    PAUSE_FROM="$(tr -d ' \t\r\n' < "$PAUSE_FROM_FILE" || true)"
fi
if [[ -n "$PAUSE_FROM" ]] && [[ "$TODAY" > "$PAUSE_FROM" || "$TODAY" == "$PAUSE_FROM" ]]; then
    export DAILY_WORK_SKIP_REPORT=1
fi

if [[ -f "$STATE_FILE" ]] && [[ "$(cat "$STATE_FILE")" == "$TODAY" ]]; then
    # 今天已跑过，跳过
    exit 0
fi

# 可选：仅工作日执行（默认关闭，cron/launchd 如需限制请在调度侧配置）
if [[ "${DAILY_WORK_WEEKDAYS_ONLY:-}" == "1" ]]; then
    # date +%u：1=周一 … 7=周日
    DOW=$(date +%u)
    if [[ "$DOW" -ge 6 ]]; then
        exit 0
    fi
fi

# 可选：仅在指定时间窗内执行（默认关闭，主要用于 launchd 的 RunAtLoad 防误跑）
# 设定方式：DAILY_WORK_WINDOW_START_MIN=565（09:25）与 DAILY_WORK_WINDOW_END_MIN=585（09:45）
if [[ -n "${DAILY_WORK_WINDOW_START_MIN:-}" && -n "${DAILY_WORK_WINDOW_END_MIN:-}" ]]; then
    HOUR=$(date +%H)
    MINUTE=$(date +%M)
    CURRENT_MINUTES=$((10#$HOUR * 60 + 10#$MINUTE))
    if [[ $CURRENT_MINUTES -lt "$DAILY_WORK_WINDOW_START_MIN" ]] || [[ $CURRENT_MINUTES -gt "$DAILY_WORK_WINDOW_END_MIN" ]]; then
        exit 0
    fi
fi

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE"; exit 1; }
[[ -f "$PYTHON_SCRIPT" ]] || { echo "Missing $PYTHON_SCRIPT"; exit 1; }

# shellcheck source=./daily_pull_env.sh
source "$ENV_FILE"
if [[ -f "$ENV_LOCAL" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_LOCAL"
fi
cd "$SCRIPT_DIR"
/usr/bin/python3 "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1
echo "$TODAY" > "$STATE_FILE"
