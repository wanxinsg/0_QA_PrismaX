#!/usr/bin/env python3
"""
每日拉取多个仓库分支并发送邮件报告

用法:
    python3 daily_pull_testing_branches.py

环境变量:
    SMTP_HOST - SMTP服务器地址 (默认: mail.privateemail.com)
    SMTP_PORT - SMTP端口 (默认: 465)
    SMTP_SECURITY - 安全类型: ssl 或 starttls (默认: ssl)
    SMTP_USER - SMTP用户名
    SMTP_PASS - SMTP密码
    EMAIL_FROM - 发件人邮箱 (默认: SMTP_USER)
    EMAIL_TO - 收件人邮箱 (默认: wanxin@solidcap.io)
    DAILY_PULL_EMAIL_SUBJECT - 邮件主题 (默认: PrismaX daily pull report)
    PROJECT_ROOT - 项目根目录 (默认: 脚本所在目录的父目录)
"""

import os
import sys
import subprocess
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Tuple

# 默认与 Prismax 主仓并列的 repo 目录名（PROJECT_ROOT 下）
REPOSITORIES = [
    "app-prismax-rp",
    "app-prismax-rp-backend",
    "gateway-prismax-rp",
    "roarm-m3-web",
    "prismax-python",
    "prismax-marketing-rp",
]

# 分支策略：默认跟踪远端 testing；个别仓库例外
DEFAULT_TARGET_BRANCH = "testing"
REPO_TARGET_BRANCHES: Dict[str, str] = {
    "prismax-python": "main",
}


class GitPullResult:
    """Git拉取结果"""
    def __init__(self, repo_name: str, repo_path: str):
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.success = False
        self.error_message = ""
        self.branch = ""
        self.latest_commit = ""
        self.commit_message = ""
        self.commit_author = ""
        self.commit_date = ""
        self.pulled = False
        self.changes_summary = ""
        self.commit_list = []  # 存储提交列表（commit hash和message）
        # pull 前、后的完整 commit SHA，供 git diff old..new（失败或未 pull 时为空字符串）
        self.old_commit_sha = ""
        self.new_commit_sha = ""

    def __str__(self):
        status = "✅ 成功" if self.success else "❌ 失败"
        return f"{self.repo_name}: {status}"


def get_project_root() -> Path:
    """获取项目根目录"""
    project_root = os.environ.get("PROJECT_ROOT")
    if project_root:
        return Path(project_root)
    
    # 默认：脚本在 Daily_Pull/ 目录下，需要向上两级到达项目根目录
    # Daily_Pull/ -> 0_QA_PrismaX/ -> Prismax/
    script_dir = Path(__file__).parent.absolute()
    return script_dir.parent.parent


def run_git_command(
    repo_path: Path, command: List[str], timeout: int = 60
) -> Tuple[bool, str, str]:
    """
    执行git命令
    
    Returns:
        (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["git"] + command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "Command timeout"
    except Exception as e:
        return False, "", str(e)


def pull_testing_branch(repo_name: str, repo_path: Path) -> GitPullResult:
    """拉取指定仓库的目标分支（默认 testing）"""
    result = GitPullResult(repo_name, str(repo_path))
    target_branch = REPO_TARGET_BRANCHES.get(repo_name, DEFAULT_TARGET_BRANCH)
    
    # 检查仓库是否存在
    if not repo_path.exists():
        result.error_message = f"仓库路径不存在: {repo_path}"
        return result
    
    if not (repo_path / ".git").exists():
        result.error_message = f"不是git仓库: {repo_path}"
        return result
    
    # 先fetch获取最新的远程分支信息
    success, stdout, stderr = run_git_command(repo_path, ["fetch", "origin"])
    if not success:
        result.error_message = f"无法fetch远程仓库: {stderr}"
        return result
    
    # 获取当前分支
    success, stdout, stderr = run_git_command(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if not success:
        result.error_message = f"无法获取当前分支: {stderr}"
        return result
    current_branch = stdout
    
    # 切换到目标分支（若当前不在目标分支）
    if current_branch != target_branch:
        # 先尝试checkout已存在的本地分支
        success, stdout, stderr = run_git_command(repo_path, ["checkout", target_branch])
        if not success:
            # 如果本地分支不存在，创建并跟踪远程分支
            success, stdout, stderr = run_git_command(
                repo_path, 
                ["checkout", "-b", target_branch, f"origin/{target_branch}"]
            )
            if not success:
                result.error_message = f"无法切换到{target_branch}分支: {stderr}"
                return result
        result.branch = target_branch
    else:
        result.branch = current_branch
    
    # 获取切换前的commit信息（用于判断是否有更新）
    success, old_commit, _ = run_git_command(repo_path, ["rev-parse", "HEAD"])
    if not success:
        result.error_message = "无法获取当前commit"
        return result
    result.old_commit_sha = old_commit
    
    # 拉取最新代码
    success, stdout, stderr = run_git_command(repo_path, ["pull", "origin", target_branch])
    if not success:
        result.error_message = f"Git pull失败: {stderr}"
        return result
    
    result.pulled = True
    
    # 获取拉取后的commit信息
    success, new_commit, _ = run_git_command(repo_path, ["rev-parse", "HEAD"])
    if success:
        result.new_commit_sha = new_commit
        result.latest_commit = new_commit[:8]  # 只显示前8位
        
        # 获取commit详细信息
        success, commit_info, _ = run_git_command(
            repo_path, 
            ["log", "-1", "--pretty=format:%s%n%an%n%ad", "--date=format:%Y-%m-%d %H:%M:%S"]
        )
        if success:
            lines = commit_info.split("\n")
            if len(lines) >= 3:
                result.commit_message = lines[0]
                result.commit_author = lines[1]
                result.commit_date = lines[2]
        
        # 检查是否有更新
        if old_commit != new_commit:
            # 获取更新摘要
            success, diff_summary, _ = run_git_command(
                repo_path,
                ["log", f"{old_commit}..{new_commit}", "--oneline", "--no-decorate"]
            )
            if success and diff_summary:
                commits = diff_summary.split("\n")
                result.changes_summary = f"更新了 {len(commits)} 个提交"
                # 存储每个提交的详细信息（hash和message）
                for commit_line in commits:
                    if commit_line.strip():
                        parts = commit_line.split(" ", 1)
                        if len(parts) >= 2:
                            result.commit_list.append({
                                "hash": parts[0],
                                "message": parts[1]
                            })
                        else:
                            result.commit_list.append({
                                "hash": parts[0],
                                "message": ""
                            })
            else:
                result.changes_summary = "有更新"
        else:
            result.changes_summary = "已是最新"
    
    result.success = True
    return result


def send_email_report(results: List[GitPullResult]):
    """发送邮件报告"""
    smtp_host = os.environ.get("SMTP_HOST", "mail.privateemail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_security = os.environ.get("SMTP_SECURITY", "ssl").lower()
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    email_to = os.environ.get("EMAIL_TO", "wanxin@solidcap.io")
    email_from = os.environ.get("EMAIL_FROM", smtp_user)
    # NOTE: 使用专用环境变量，避免与其他 cron 任务共用 EMAIL_SUBJECT 造成标题串台
    subject = os.environ.get("DAILY_PULL_EMAIL_SUBJECT", "PrismaX daily pull report")
    
    if not smtp_user or not smtp_pass:
        print("⚠️  SMTP_USER/SMTP_PASS 未设置，跳过邮件发送")
        return
    
    # 构建HTML邮件内容
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
            .summary {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .repo {{ margin: 20px 0; padding: 15px; border-left: 4px solid #3498db; background: #f8f9fa; }}
            .repo.success {{ border-left-color: #27ae60; }}
            .repo.failed {{ border-left-color: #e74c3c; }}
            .repo-name {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
            .info {{ margin: 5px 0; }}
            .label {{ font-weight: bold; color: #555; }}
            .error {{ color: #e74c3c; font-weight: bold; }}
            .commit-info {{ background: white; padding: 10px; border-radius: 3px; margin-top: 10px; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #777; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📦 PrismaX daily pull report</h1>
            <div class="summary">
                <p><strong>执行时间:</strong> {now}</p>
                <p><strong>总计:</strong> {len(results)} 个仓库</p>
                <p><strong>分支策略:</strong> 默认跟踪 testing；prismax-python 跟踪 main</p>
                <p><strong>成功:</strong> <span style="color: #27ae60;">{sum(1 for r in results if r.success)}</span></p>
                <p><strong>失败:</strong> <span style="color: #e74c3c;">{sum(1 for r in results if not r.success)}</span></p>
            </div>
    """
    
    for result in results:
        status_class = "success" if result.success else "failed"
        status_icon = "✅" if result.success else "❌"
        
        html_body += f"""
            <div class="repo {status_class}">
                <div class="repo-name">{status_icon} {result.repo_name}</div>
        """
        
        if result.success:
            html_body += f"""
                <div class="info"><span class="label">路径:</span> {result.repo_path}</div>
                <div class="info"><span class="label">分支:</span> {result.branch}</div>
                <div class="info"><span class="label">状态:</span> {result.changes_summary}</div>
            """
            
            # 如果有更新的提交列表，显示每个提交
            if result.commit_list:
                html_body += """
                <div class="info"><span class="label">提交列表:</span></div>
                <ul style="margin: 5px 0; padding-left: 30px;">
                """
                for commit in result.commit_list:
                    html_body += f"""
                    <li style="margin: 3px 0;"><code style="background: #e8e8e8; padding: 2px 4px; border-radius: 2px;">{commit['hash']}</code> {commit['message']}</li>
                    """
                html_body += """
                </ul>
                """
            
            if result.latest_commit:
                html_body += f"""
                <div class="commit-info">
                    <div class="info"><span class="label">最新提交:</span> {result.latest_commit}</div>
                    <div class="info"><span class="label">提交信息:</span> {result.commit_message}</div>
                    <div class="info"><span class="label">作者:</span> {result.commit_author}</div>
                    <div class="info"><span class="label">时间:</span> {result.commit_date}</div>
                </div>
                """
        else:
            html_body += f"""
                <div class="info"><span class="label">路径:</span> {result.repo_path}</div>
                <div class="error">错误: {result.error_message}</div>
            """
        
        html_body += "</div>"
    
    html_body += """
            <div class="footer">
                <p>此邮件由 Prismax QA 自动化脚本自动发送</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # 创建邮件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    
    # 添加HTML内容
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    # 发送邮件
    try:
        context = ssl.create_default_context()
        if smtp_security == "ssl" or smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(email_from, [email_to], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.sendmail(email_from, [email_to], msg.as_string())
        
        print(f"✅ 邮件已成功发送到: {email_to}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        raise


def main():
    """主函数"""
    print("=" * 60)
    print("Prismax 每日分支拉取脚本")
    print("=" * 60)
    
    project_root = get_project_root()
    print(f"项目根目录: {project_root}")
    
    results = []
    
    for repo_name in REPOSITORIES:
        repo_path = project_root / repo_name
        print(f"\n处理仓库: {repo_name}")
        print(f"路径: {repo_path}")
        
        result = pull_testing_branch(repo_name, repo_path)
        results.append(result)
        
        if result.success:
            print(f"✅ {repo_name}: {result.changes_summary}")
            if result.latest_commit:
                print(f"   最新提交: {result.latest_commit} - {result.commit_message}")
        else:
            print(f"❌ {repo_name}: {result.error_message}")
    
    # 发送邮件报告
    print("\n" + "=" * 60)
    print("发送邮件报告...")
    send_email_report(results)
    
    # 打印总结
    print("\n" + "=" * 60)
    print("执行总结:")
    print(f"  总计: {len(results)} 个仓库")
    print(f"  成功: {sum(1 for r in results if r.success)}")
    print(f"  失败: {sum(1 for r in results if not r.success)}")
    print("=" * 60)
    
    # 如果有失败，返回非零退出码
    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
