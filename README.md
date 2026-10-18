# PrismaX QA Knowledge

本仓库保存产品 QA 文档、需求资料、发布记录和系统知识。可执行的上传工具、自动化测试框架和本地数据不放在这里。

## 目录

| 目录 | 内容 |
| --- | --- |
| `feature_tests/` | 当前 Sprint 的功能分析、测试设计和测试用例 |
| `product_requirements/` | PRD、设计说明及需求相关参考实现 |
| `release_notes/` | Release Note、Jira 导出和发布记录 |
| `knowledge_base/` | 系统、数据、MCAP 和业务知识 |
| `release_process/` | 发布流程与操作规范 |
| `archive/` | 已完成或停止维护的历史 QA 文档 |
| `Fresh_cheese/` | 独立资料区；本次目录整理不修改其内容 |

## 存放原则

- 产品行为、测试范围和发布知识放在本仓库。
- 可重复执行的脚本放入 `0_QA_Assistance`。
- pytest、Playwright、API 与 SDK 测试放入 `0_QA_TestFramework`。
- 视频、MCAP、运行日志和临时导出保存在工作区 `_local_data/`，不提交到 Git。
