# Release Note 写作模板

**本模板为所有 Release Note 的统一写作规范，今后 RN 均按此模板撰写。**

## 使用方式
1. 从 `ReleaseNoteList.csv` 导出本迭代的 Issue 列表（筛选 Issue Type、Key、Summary）。
2. **Task** → 归入 **New Features & Improvements**
3. **Bug** → 归入 **Bug Fixes**
4. 按主题分组、合并相似项，语言改写成面向用户的简短说明。
5. **不包含 Admin**：管理后台的改动不写入 Release Note。

---

## 文档结构

```
Release Note [版本号] ([时间范围])

## New Features & Improvements

- 简短描述 1
- 简短描述 2
- 简短描述 3
（不写出分组标题，但按分组主题顺序排列，见下方「分组参考」）

## Bug Fixes

- 简短描述 1
- 简短描述 2
```

---

## 写作原则

| 原则 | 说明 |
|------|------|
| **简洁** | 每条一句话，避免技术黑话；用户能看懂「做了什么」「解决了什么」。 |
| **分组** | New Features 与 Bug Fixes 均不写出分组标题，仅用条目标题；两条目均按分组主题顺序排列（Arm → Queue & Tele-op → Blockchain & Wallet → Account & Security → Leaderboard & Points）。 |
| **用户视角** | 写「用户能得到什么」或「什么问题被修复」，不写 Jira Key 或实现细节。 |
| **可略过** | 纯内部/运营类（如「写 change summary」「停榜」）、面向 developer 的说明（如「restart arm 说明」）、内部 tech 优化（如「email validation 校验」）不写入。 |
| **不写 Admin** | 管理后台（Admin Portal）的修改不放入 Release Note，用户无需知晓。 |

---

## 分组参考（可按实际调整，New Features 条目按此顺序排列）

1. **Arm** — 新增 Arm、Training Arm、Partner Arm 等
2. **Queue & Tele-op** — 排队、远程控制、直播
3. **Blockchain & Wallet** — 链、钱包、支付相关（仅用户端）
4. **Account & Security** — 账号、登录、验证
5. **Leaderboard & Points** — 积分、排行榜、活动
