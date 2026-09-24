#!/usr/bin/env python3
"""
每日拉取多个仓库分支并发送邮件报告。

分支策略:
    - 默认: testing
    - prismax-python: main

用法:
    python3 daily_pull_branches.py
"""

from daily_pull_testing_branches import (  # noqa: F401
    DEFAULT_TARGET_BRANCH,
    REPO_TARGET_BRANCHES,
    REPOSITORIES,
    GitPullResult,
    get_project_root,
    pull_testing_branch,
    run_git_command,
    send_email_report,
    main,
)


if __name__ == "__main__":
    main()
