#!/bin/bash
#
# 设置 Daily Work 的 Cron 任务（与 launchd 一致：工作日 + run_daily_pull_once 时间窗）
#
# 用法:
#   ./setup_cron.sh [hour] [minute]
#
# 参数:
#   hour   - 运行时间的小时 (0-23, 默认: 9)
#   minute - 运行时间的分钟 (0-59, 默认: 30，落在 9:25–9:45 窗口内)
#
# 示例:
#   ./setup_cron.sh           # 每周一至五 9:30
#   ./setup_cron.sh 9 35      # 每周一至五 9:35
#

set -euo pipefail

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAILY_PULL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DAILY_PULL_DIR}/daily_pull_env.sh"
WRAPPER_SCRIPT="${SCRIPT_DIR}/run_daily_pull_once.sh"
LOG_FILE="${SCRIPT_DIR}/daily_pull.log"

# 检查文件是否存在
if [ ! -f "$ENV_FILE" ]; then
    echo "错误: 找不到环境变量配置文件: $ENV_FILE"
    exit 1
fi

if [ ! -f "$WRAPPER_SCRIPT" ]; then
    echo "错误: 找不到: $WRAPPER_SCRIPT"
    exit 1
fi

# 获取运行时间（默认 9:30，需在 run_daily_pull_once 的 9:25–9:45 窗口内）
HOUR="${1:-9}"
MINUTE="${2:-30}"

# 验证时间参数
if ! [[ "$HOUR" =~ ^[0-9]+$ ]] || [ "$HOUR" -lt 0 ] || [ "$HOUR" -gt 23 ]; then
    echo "错误: 小时必须是0-23之间的数字"
    exit 1
fi

if ! [[ "$MINUTE" =~ ^[0-9]+$ ]] || [ "$MINUTE" -lt 0 ] || [ "$MINUTE" -gt 59 ]; then
    echo "错误: 分钟必须是0-59之间的数字"
    exit 1
fi

# 构建 cron 任务（周一至周五）
CRON_TIME="$MINUTE $HOUR * * 1-5"
CRON_COMMAND="source $ENV_FILE && $WRAPPER_SCRIPT >> $LOG_FILE 2>&1"
CRON_ENTRY="$CRON_TIME $CRON_COMMAND"

# 检查是否已存在相同的 cron 任务
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -F "run_daily_pull_once.sh" || true)

if [ -n "$EXISTING_CRON" ]; then
    echo "⚠️  检测到已存在的cron任务:"
    echo "   $EXISTING_CRON"
    echo ""
    read -p "是否要替换现有任务? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消操作"
        exit 0
    fi
    
    # 删除旧任务
    (crontab -l 2>/dev/null | grep -vF "run_daily_pull_once.sh") | crontab -
    echo "✅ 已删除旧任务"
fi

# 添加新任务
(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo "✅ Cron任务已设置成功！"
echo ""
echo "任务详情:"
echo "  时间: 工作日 $HOUR:$MINUTE（周一~周五）"
echo "  命令: $CRON_COMMAND"
echo "  日志: $LOG_FILE"
echo ""
echo "查看当前cron任务:"
echo "  crontab -l"
echo ""
echo "编辑cron任务:"
echo "  crontab -e"
echo ""
echo "删除cron任务:"
echo "  crontab -l | grep -v 'run_daily_pull_once.sh' | crontab -"
echo ""
echo "⚠️  请确保已正确配置环境变量文件: $ENV_FILE"
