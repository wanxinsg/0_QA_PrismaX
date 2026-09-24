#!/usr/bin/env python3
"""
工作日 Daily Work：拉取各仓库目标分支并发邮件。

用法:
    python3 daily_work_pipeline.py
"""

from __future__ import annotations

import sys
from typing import List

from daily_pull_branches import (
    REPOSITORIES,
    GitPullResult,
    get_project_root,
    pull_testing_branch,
    send_email_report,
)


def main() -> None:
    print("=" * 60)
    print("Prismax Daily Work（拉取 + 发送邮件）")
    print("=" * 60)

    project_root = get_project_root()
    print(f"项目根目录: {project_root}")

    results: List[GitPullResult] = []
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

    print("\n" + "=" * 60)
    print("发送邮件报告...")
    try:
        send_email_report(results)
    except Exception as e:
        print(f"⚠️  邮件发送失败（已忽略）: {e}")

    print("\n" + "=" * 60)
    print("执行总结:")
    print(f"  总计: {len(results)} 个仓库")
    print(f"  成功: {sum(1 for r in results if r.success)}")
    print(f"  失败: {sum(1 for r in results if not r.success)}")
    print("=" * 60)

    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
