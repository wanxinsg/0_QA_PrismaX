#!/bin/bash
#
# Prismax Git Pull Automation Script (Kira-compatible mechanism)
# - Pull repos (default testing; prismax-python tracks main)
# - Send unified HTML email report (same template/subject strategy as Kira)
# - Stamp to avoid double-run in same day
#

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PRISMAX_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAST_PULL_DATE_FILE="$SCRIPT_DIR/.last_pull_date"
LOCK_DIR="$SCRIPT_DIR/.pull_repos.lock"

# Where to write "email sent at" stamp for Regression gating
SENT_AT_FILE="$QA_ROOT/Daily_Regression_Test/tele_op_services/.daily_pull_sent_at"

TODAY="$(date '+%Y-%m-%d')"
# Idempotency: if already completed today, exit (avoid double emails from multiple schedulers)
if [ -f "$LAST_PULL_DATE_FILE" ]; then
    LAST="$(cat "$LAST_PULL_DATE_FILE" 2>/dev/null || true)"
    if [ -n "$LAST" ] && [ "$LAST" = "$TODAY" ] && [ "${FORCE_RUN:-}" != "1" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Skip: already completed today ($TODAY)."
        exit 0
    fi
fi

# Prevent concurrent daily/catch-up runs without marking the day complete before email succeeds.
if [ "${FORCE_RUN:-}" != "1" ]; then
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Skip: another pull_repos.sh is already running."
        exit 0
    fi
    trap 'rm -rf "$LOCK_DIR"' EXIT
fi

# Load Prismax env file(s) explicitly. Do not source ~/.zshrc here: zsh-specific
# startup files may exit/return when sourced by bash, aborting this script.
ENV_FILE="$SCRIPT_DIR/daily_pull_env.sh"
ENV_LOCAL="$SCRIPT_DIR/daily_pull_env.local.sh"
if [ -f "$ENV_FILE" ]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi
if [ -f "$ENV_LOCAL" ]; then
    # shellcheck source=/dev/null
    source "$ENV_LOCAL"
fi

# Define repositories to pull
REPOS=(
    "app-prismax-rp"
    "app-prismax-rp-backend"
    "gateway-prismax-rp"
    "roarm-m3-web"
    "prismax-python"
    "prismax-marketing-rp"
)

DEFAULT_TARGET_BRANCH="testing"

# 个别仓库不跟踪 testing
target_branch_for() {
    case "$1" in
        prismax-python) echo "main" ;;
        *) echo "$DEFAULT_TARGET_BRANCH" ;;
    esac
}

# Function to log messages
log_message() {
    local message="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $message"
}

get_current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null
}

get_commit_info() {
    git log -1 --pretty=format:"%h - %s (%an, %ar)" 2>/dev/null
}

escape_html() {
    echo "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g'
}

REPO_HTML_BLOCKS=""
SUCCESS_COUNT=0
FAILURE_COUNT=0
SKIP_COUNT=0
UPDATE_COUNT=0

log_message "=========================================="
log_message "Starting Prismax Git Pull Automation"
log_message "=========================================="

for repo in "${REPOS[@]}"; do
    REPO_PATH="$PRISMAX_ROOT/$repo"
    TARGET_BRANCH="$(target_branch_for "$repo")"

    log_message ""
    log_message "Processing: $repo"
    log_message "Path: $REPO_PATH"

    if [ ! -d "$REPO_PATH" ]; then
        SAFE_ERR=$(escape_html "Directory not found")
        REPO_HTML_BLOCKS="$REPO_HTML_BLOCKS
            <div class=\"repo failed\">
                <div class=\"repo-name\">❌ $repo</div>
                <div class=\"info\"><span class=\"label\">路径:</span> $REPO_PATH</div>
                <div class=\"error\">错误: $SAFE_ERR</div>
            </div>"
        ((FAILURE_COUNT++))
        continue
    fi

    cd "$REPO_PATH" || {
        SAFE_ERR=$(escape_html "Cannot access directory")
        REPO_HTML_BLOCKS="$REPO_HTML_BLOCKS
            <div class=\"repo failed\">
                <div class=\"repo-name\">❌ $repo</div>
                <div class=\"info\"><span class=\"label\">路径:</span> $REPO_PATH</div>
                <div class=\"error\">错误: $SAFE_ERR</div>
            </div>"
        ((FAILURE_COUNT++))
        continue
    }

    if [ ! -d ".git" ]; then
        SAFE_ERR=$(escape_html "Not a git repository")
        REPO_HTML_BLOCKS="$REPO_HTML_BLOCKS
            <div class=\"repo failed\">
                <div class=\"repo-name\">❌ $repo</div>
                <div class=\"info\"><span class=\"label\">路径:</span> $REPO_PATH</div>
                <div class=\"error\">错误: $SAFE_ERR</div>
            </div>"
        ((FAILURE_COUNT++))
        continue
    fi

    CURRENT_BRANCH=$(get_current_branch)
    log_message "Current branch: $CURRENT_BRANCH"

    BEFORE_COMMIT=$(get_commit_info)
    SAFE_BEFORE=$(escape_html "$BEFORE_COMMIT")

    log_message "Fetching latest changes..."
    git fetch origin > /dev/null 2>&1

    if ! git diff-index --quiet HEAD --; then
        log_message "Local changes detected, stashing..."
        git stash save "Auto-stash before pull on $(date '+%Y-%m-%d %H:%M:%S')" > /dev/null 2>&1
    fi

    # Ensure on the target branch
    if [ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]; then
        log_message "Switching to $TARGET_BRANCH..."
        git checkout "$TARGET_BRANCH" > /dev/null 2>&1 || \
        git checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH" > /dev/null 2>&1
    fi

    log_message "Pulling latest changes from $TARGET_BRANCH..."
    PULL_OUTPUT=$(git pull origin "$TARGET_BRANCH" 2>&1)
    PULL_EXIT_CODE=$?

    if [ $PULL_EXIT_CODE -eq 0 ]; then
        AFTER_COMMIT=$(get_commit_info)
        SAFE_AFTER=$(escape_html "$AFTER_COMMIT")
        if [ "$BEFORE_COMMIT" = "$AFTER_COMMIT" ]; then
            REPO_HTML_BLOCKS="$REPO_HTML_BLOCKS
            <div class=\"repo success\">
                <div class=\"repo-name\">✅ $repo</div>
                <div class=\"info\"><span class=\"label\">路径:</span> $REPO_PATH</div>
                <div class=\"info\"><span class=\"label\">分支:</span> $TARGET_BRANCH</div>
                <div class=\"info\"><span class=\"label\">状态:</span> Already up to date</div>
                <div class=\"commit-info\">
                    <div class=\"info\"><span class=\"label\">最新提交:</span> $SAFE_AFTER</div>
                </div>
            </div>"
        else
            REPO_HTML_BLOCKS="$REPO_HTML_BLOCKS
            <div class=\"repo success\">
                <div class=\"repo-name\">✅ $repo</div>
                <div class=\"info\"><span class=\"label\">路径:</span> $REPO_PATH</div>
                <div class=\"info\"><span class=\"label\">分支:</span> $TARGET_BRANCH</div>
                <div class=\"info\"><span class=\"label\">状态:</span> Updated</div>
                <div class=\"commit-info\">
                    <div class=\"info\"><span class=\"label\">Before:</span> $SAFE_BEFORE</div>
                    <div class=\"info\"><span class=\"label\">After:</span> $SAFE_AFTER</div>
                </div>
            </div>"
            ((UPDATE_COUNT++))
        fi
        ((SUCCESS_COUNT++))
    else
        PULL_ERR_FIRST=$(echo "$PULL_OUTPUT" | head -n 1)
        SAFE_ERR=$(escape_html "$PULL_ERR_FIRST")
        REPO_HTML_BLOCKS="$REPO_HTML_BLOCKS
            <div class=\"repo failed\">
                <div class=\"repo-name\">❌ $repo</div>
                <div class=\"info\"><span class=\"label\">路径:</span> $REPO_PATH</div>
                <div class=\"info\"><span class=\"label\">分支:</span> $TARGET_BRANCH</div>
                <div class=\"error\">错误: $SAFE_ERR</div>
            </div>"
        ((FAILURE_COUNT++))
    fi
done

# Determine email subject based on results (same strategy as Kira)
if [ $UPDATE_COUNT -gt 0 ]; then
    EMAIL_SUBJECT="[🔥 $UPDATE_COUNT UPDATES] PRISMAX_daily_pull report - $(date '+%Y-%m-%d')"
elif [ $FAILURE_COUNT -gt 0 ]; then
    EMAIL_SUBJECT="[FAILED] PRISMAX_daily_pull report - $(date '+%Y-%m-%d')"
elif [ $SKIP_COUNT -gt 0 ]; then
    EMAIL_SUBJECT="[WARNING] PRISMAX_daily_pull report - $(date '+%Y-%m-%d')"
else
    EMAIL_SUBJECT="[SUCCESS] PRISMAX_daily_pull report - $(date '+%Y-%m-%d')"
fi

NOW_STR=$(date '+%Y-%m-%d %H:%M:%S')
EMAIL_BODY=$(cat << MAILBODY
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        .summary { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .repo { margin: 20px 0; padding: 15px; border-left: 4px solid #3498db; background: #f8f9fa; }
        .repo.success { border-left-color: #27ae60; }
        .repo.failed { border-left-color: #e74c3c; }
        .repo-name { font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }
        .info { margin: 5px 0; }
        .label { font-weight: bold; color: #555; }
        .error { color: #e74c3c; font-weight: bold; }
        .commit-info { background: white; padding: 10px; border-radius: 3px; margin-top: 10px; }
        .footer { margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #777; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📦 PRISMAX daily pull report</h1>
        <div class="summary">
            <p><strong>执行时间:</strong> $NOW_STR</p>
            <p><strong>总计:</strong> ${#REPOS[@]} 个仓库</p>
            <p><strong>分支策略:</strong> 默认跟踪 testing；prismax-python 跟踪 main</p>
            <p><strong>成功:</strong> <span style="color: #27ae60;">$SUCCESS_COUNT</span></p>
            <p><strong>失败:</strong> <span style="color: #e74c3c;">$FAILURE_COUNT</span></p>
            <p><strong>跳过:</strong> <span style="color: #f39c12;">$SKIP_COUNT</span></p>
        </div>
$REPO_HTML_BLOCKS
        <div class="footer">
            <p>此邮件由 PRISMAX QA 自动化脚本自动发送</p>
        </div>
    </div>
</body>
</html>
MAILBODY
)

python3 << EOF
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

smtp_host = os.environ.get('SMTP_HOST') or os.environ.get('SMTP_SERVER') or 'smtp.gmail.com'
smtp_port = int(os.environ.get('SMTP_PORT', '465'))
smtp_security = (os.environ.get('SMTP_SECURITY') or '').strip().lower()
smtp_user = os.environ.get('SMTP_USER', '')
smtp_pass = os.environ.get('SMTP_PASS') or os.environ.get('SMTP_PASSWORD') or ''
email_to = os.environ.get('EMAIL_TO', smtp_user)

if not smtp_user or not smtp_pass:
    print("ERROR: SMTP credentials not found in environment variables")
    print("Please set SMTP_USER and SMTP_PASS (or SMTP_PASSWORD)")
    raise SystemExit(1)

msg = MIMEMultipart('alternative')
msg['Subject'] = "$EMAIL_SUBJECT"
msg['From'] = smtp_user
msg['To'] = email_to
msg.attach(MIMEText("""$EMAIL_BODY""", 'html'))

try:
    # Port-based default behavior if SMTP_SECURITY is not explicitly set
    use_ssl = (smtp_security == "ssl") or (smtp_port == 465 and smtp_security != "starttls")
    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    print("Email sent successfully to: " + email_to)
except Exception as e:
    print(f"ERROR: Failed to send email: {e}")
    raise SystemExit(1)
EOF

EMAIL_EXIT_CODE=$?
if [ $EMAIL_EXIT_CODE -eq 0 ]; then
    log_message "Email notification sent successfully"
    echo "$TODAY" > "$LAST_PULL_DATE_FILE"
    mkdir -p "$(dirname "$SENT_AT_FILE")" 2>/dev/null || true
    echo "$NOW_STR" > "$SENT_AT_FILE"
    log_message "Wrote daily pull sent_at: $SENT_AT_FILE"
else
    log_message "ERROR: Failed to send email notification"
fi

if [ $FAILURE_COUNT -gt 0 ] || [ $EMAIL_EXIT_CODE -ne 0 ]; then
    exit 1
fi
exit 0

