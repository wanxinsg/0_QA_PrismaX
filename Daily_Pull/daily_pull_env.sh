#!/bin/bash
#
# Daily Pull 环境变量配置文件
# 用于cron任务中设置环境变量
#
# 使用方法:
#   source /Users/wanxin/PycharmProjects/WORK/Prismax/0_QA_PrismaX/Daily_Pull/daily_pull_env.sh
#

# SMTP服务器配置
export SMTP_HOST="${SMTP_HOST:-mail.privateemail.com}"
export SMTP_PORT="${SMTP_PORT:-465}"
export SMTP_SECURITY="${SMTP_SECURITY:-ssl}"

# SMTP认证信息
export SMTP_USER="${SMTP_USER:-wanxin@solidcap.io}"
export SMTP_PASS="${SMTP_PASS:-Test@666}"

# 邮件发送配置
export EMAIL_FROM="${EMAIL_FROM:-${SMTP_USER}}"
export EMAIL_TO="${EMAIL_TO:-wanxin@solidcap.io}"
# NOTE:
# - 这里强制为 daily pull 设置独立的标题变量，避免系统/其他任务里遗留的 EMAIL_SUBJECT 影响本任务
# - 同时继续导出 EMAIL_SUBJECT 以兼容旧脚本/调用方式
export DAILY_PULL_EMAIL_SUBJECT="${DAILY_PULL_EMAIL_SUBJECT:-PrismaX daily pull report}"
export EMAIL_SUBJECT="$DAILY_PULL_EMAIL_SUBJECT"

# 项目根目录（可选，默认自动检测）
# export PROJECT_ROOT="/Users/wanxin/PycharmProjects/WORK/Prismax"

# --- Daily Work LLM（daily_work_pipeline.py）---
# 敏感项建议写入同目录 daily_pull_env.local.sh（已被 .gitignore）
#
# LLM_PROVIDER=cursor         # cursor | openai | anthropic（cursor=仅生成 MD+提示，在 Cursor 里补全分析，不占 API）
# LLM_PROVIDER=openai         # openai | anthropic
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-3-5-haiku-20241022
# SKIP_LLM_IF_NO_COMMITS=1    # 1=四库均无新 commit 则不调用 API（省费用）
# DAILY_WORK_MAX_PATCH_CHARS=120000
# DAILY_WORK_MAX_PATCH_FILES=40
# LLM_TIMEOUT_SEC=180
