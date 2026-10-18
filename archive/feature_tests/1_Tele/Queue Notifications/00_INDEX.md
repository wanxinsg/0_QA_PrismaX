# 队列通知功能 (PRIS-84) 测试文档索引

## 📋 文档概览

本目录包含 PrismaX 队列通知功能（PRIS-84）的完整测试文档。

---

## 📚 文档列表

### 1. 📖 **测试导航指南** - 从这里开始
**文件**: `README_QUEUE_NOTIFICATION_TESTING.md`  
**适用人群**: 所有测试相关人员  
**阅读时间**: 5 分钟

**简介**: 
- 快速导航指南
- 新手入门步骤
- 测试技巧和工具
- 文档使用说明

**何时阅读**: 首次接触该功能测试时

---

### 2. 📊 **测试策略分析** - 深度理解
**文件**: `QUEUE_NOTIFICATION_TEST_STRATEGY_ANALYSIS.md`  
**适用人群**: QA Lead, 产品经理, 开发负责人  
**阅读时间**: 15-20 分钟

**简介**:
- 功能深度分析（含代码解读）
- 测试方法论和策略
- 风险评估与缓解措施
- 验收标准和 KPI 指标
- 测试改进建议

**何时阅读**: 
- 需要了解整体测试策略时
- 制定测试计划时
- 评估发布风险时

---

### 3. ✅ **手工测试用例** - 执行测试
**文件**: `QUEUE_NOTIFICATION_MANUAL_TEST_CASES.md`  
**适用人群**: QA 测试工程师  
**执行时间**: 3-4 小时（完整测试）

**简介**:
- **30 个详细测试用例**
- **10 个测试模块**
- 分步骤执行指南
- 预期结果和实际结果记录表
- 缺陷报告模板

**何时使用**: 执行功能测试时

**测试模块**:
- A. 通知权限请求 - 桌面端 (6用例)
- B. 通知权限请求 - 移动端 (1用例)
- C. 通知触发 - 位置 #6 (2用例)
- D. 通知触发 - 位置 #2 (3用例)
- E. 防止重复通知 (2用例)
- F. 状态重置 (2用例)
- G. 边界条件 (4用例)
- H. 跨浏览器兼容性 (5用例)
- I. 用户体验与性能 (4用例)
- J. 回归测试 (1用例)

---

## 🎯 快速开始流程

### 对于测试执行人员

```
步骤 1: 阅读 README_QUEUE_NOTIFICATION_TESTING.md
        ↓
步骤 2: 准备测试环境和工具
        ↓
步骤 3: 执行 QUEUE_NOTIFICATION_MANUAL_TEST_CASES.md 中的用例
        ↓
步骤 4: 记录结果并提交缺陷报告
```

### 对于测试管理人员

```
步骤 1: 阅读 QUEUE_NOTIFICATION_TEST_STRATEGY_ANALYSIS.md
        ↓
步骤 2: 审阅测试用例和验收标准
        ↓
步骤 3: 分配测试任务
        ↓
步骤 4: 监控测试进度和质量
        ↓
步骤 5: 评估发布准备度
```

---

## 📈 测试统计

### 测试用例分布
```
总用例数: 30
├─ P0 (Blocker):    11 个  🔴 必须 100% 通过
├─ P1 (Critical):   14 个  🟠 建议 ≥95% 通过
└─ P2 (Major):       5 个  🟡 建议 ≥90% 通过
```

### 浏览器覆盖
- ✅ Chrome 120+ (P0)
- ✅ Firefox 120+ (P1)
- ✅ Safari 17+ (P1)
- ✅ Edge 120+ (P2)
- ✅ iOS Safari (P1)
- ✅ Android Chrome (P1)

### 预计执行时间
- **冒烟测试**: 30 分钟（P0 用例）
- **功能测试**: 2 小时（P0 + P1）
- **完整测试**: 3-4 小时（所有用例）

---

## 🔗 相关链接

### 项目相关
- **Jira Ticket**: [PRIS-84](https://prismax.atlassian.net/browse/PRIS-84)
- **PR #11**: [添加浏览器队列通知](https://github.com/PrismaXAI/app-prismax-rp/pull/11)
- **PR #12**: [优化移动端体验](https://github.com/PrismaXAI/app-prismax-rp/pull/12)
- **源代码**: `/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp/`

### Git 提交记录
```
a7588c2 - 添加浏览器队列通知 (2026-01-16)
faecce5 - 重置通知标志并优化移动端体验 (2026-01-20)
72c5a34 - 合并 PR #12 (2026-01-20)
```

### 技术文档
- [Notification API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API)
- [Socket.IO Client API](https://socket.io/docs/v4/client-api/)
- [React useRef Hook](https://react.dev/reference/react/useRef)

---

## 🎯 功能概述

### 核心功能
队列通知系统通过浏览器原生通知 API，在用户队列位置接近轮次时发送提醒，避免用户错过控制机会。

### 关键特性
1. **智能通知触发**
   - 位置 #6: 第一次提醒 "It's almost your turn!"
   - 位置 #2: 第二次提醒 "You're up next!"

2. **权限管理**
   - 桌面端显示友好的权限请求 UI
   - 移动端自动适配（不显示提示框）

3. **防重复机制**
   - 同一位置不重复发送通知
   - Fast Track 后正确管理状态
   - 状态在离开队列或激活控制后重置

4. **跨平台支持**
   - 支持 Chrome, Firefox, Safari, Edge
   - 桌面和移动端差异化处理
   - 优雅降级（不影响核心功能）

---

## ✅ 测试完成标准

### 发布准入标准
- [ ] 所有 P0 用例 100% 通过
- [ ] 无 P0/P1 级别未修复缺陷
- [ ] Chrome 浏览器 100% 兼容
- [ ] 核心队列功能不受影响
- [ ] P1 用例通过率 ≥ 95%

### 测试报告要求
- [ ] 所有测试用例已执行并记录
- [ ] 缺陷已在 Jira 中创建并跟踪
- [ ] 测试摘要报告已提交
- [ ] 发布风险评估已完成

---

## 🐛 缺陷管理

### 缺陷报告
- **标题格式**: `[PRIS-84] [模块名] 简短描述`
- **优先级**: P0 (Blocker) / P1 (Critical) / P2 (Major)
- **必需附件**: 截图、视频、控制台日志
- **复现步骤**: 详细、可重复

### 缺陷跟踪
- 在 `QUEUE_NOTIFICATION_MANUAL_TEST_CASES.md` 中记录缺陷 ID
- 在 Jira 中关联测试用例 ID
- 修复后进行验证测试

---

## 👥 团队联系方式

### 测试团队
- **QA Lead**: _______________
- **功能测试**: _______________
- **兼容性测试**: _______________

### 开发团队
- **功能负责人**: Aparna Rangamani
- **Code Reviewer**: _______________

### 产品团队
- **Product Manager**: _______________
- **UX Designer**: _______________

---

## 📝 文档版本

| 文档 | 版本 | 创建日期 | 最后更新 |
|------|------|---------|---------|
| 测试导航指南 | 1.0 | 2026-01-21 | 2026-01-21 |
| 测试策略分析 | 1.0 | 2026-01-21 | 2026-01-21 |
| 手工测试用例 | 1.0 | 2026-01-21 | 2026-01-21 |

---

## 💡 使用提示

1. **首次使用**: 从 `README_QUEUE_NOTIFICATION_TESTING.md` 开始
2. **执行测试**: 直接查看 `QUEUE_NOTIFICATION_MANUAL_TEST_CASES.md`
3. **深入理解**: 阅读 `QUEUE_NOTIFICATION_TEST_STRATEGY_ANALYSIS.md`
4. **遇到问题**: 查阅文档中的"测试技巧"部分或联系团队

---

## 📂 目录结构

```
Queue Notifications/
├── 00_INDEX.md                                      [本文件]
├── README_QUEUE_NOTIFICATION_TESTING.md             [测试导航指南]
├── QUEUE_NOTIFICATION_TEST_STRATEGY_ANALYSIS.md     [测试策略分析]
└── QUEUE_NOTIFICATION_MANUAL_TEST_CASES.md          [手工测试用例]
```

---

**文档所有者**: QA Team  
**维护频率**: 每次发布后更新  
**下次审核**: 2026-02-21

---

**祝测试顺利！** 🚀
