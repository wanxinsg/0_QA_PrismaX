#!/bin/bash
#
# 每日拉取多个仓库分支并发送邮件报告（全部跟踪 testing）
#
# 用法:
#   ./daily_pull_testing_branches.sh
#
# 环境变量配置（可选）:
#   export SMTP_HOST=mail.privateemail.com
#   export SMTP_PORT=465
#   export SMTP_SECURITY=ssl
#   export SMTP_USER=your_email@example.com
#   export SMTP_PASS=your_password
#   export EMAIL_FROM=your_email@example.com
#   export EMAIL_TO=wanxin@solidcap.io
#   export EMAIL_SUBJECT="Prismax 每日拉取报告（testing）"
#   export PROJECT_ROOT=/path/to/Prismax
#

set -euo pipefail

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/daily_pull_testing_branches.py"

# 检查Python脚本是否存在
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "错误: 找不到Python脚本: $PYTHON_SCRIPT"
    exit 1
fi

# 运行Python脚本
python3 "$PYTHON_SCRIPT" "$@"
