#!/usr/bin/env bash
#
# Tele-Op Regression Cron 包装脚本
# 用于定时任务：先加载 SMTP 等环境变量，再执行 run_tests.sh，确保邮件能发送
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1) 优先使用同目录下的私有配置（不提交到 git，仅本机）
if [[ -f "$SCRIPT_DIR/.tele_op_cron_env" ]]; then
  source "$SCRIPT_DIR/.tele_op_cron_env"
fi

# 2) 若未设置 SMTP 凭证，尝试从 Daily_Pull 的环境文件加载（与 Daily Pull 共用一套 SMTP）
DAILY_PULL_ENV="$(cd "$SCRIPT_DIR/../../Daily_Pull" && pwd)/daily_pull_env.sh"
if [[ -f "$DAILY_PULL_ENV" ]]; then
  source "$DAILY_PULL_ENV"
fi

# 3) 邮件标题：带日期的 Tele-Op 回归测试
export TELEOP_REGRESSION_EMAIL_SUBJECT="${TELEOP_REGRESSION_EMAIL_SUBJECT:-$(date '+%Y-%m-%d') Tele-Op Daily Regression Test}"

# 4) 执行测试（会发邮件）
cd "$SCRIPT_DIR"
exec /usr/bin/env bash ./run_tests.sh "$@"
