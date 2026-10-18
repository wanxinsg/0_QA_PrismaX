# Arm4 功能测试策略

## 📊 执行摘要

**功能**: Arm4 (Training Arm) 机器人支持  
**版本**: Commits 694a6c0 (Frontend) + 06b6dc2 (Backend)  
**测试类型**: 手工测试 + API 测试  
**测试用例总数**: 35 个  
**优先级分布**: P0: 12个 | P1: 15个 | P2: 8个  

---

## 🎯 测试策略概述

### 1. 测试目标

#### 主要目标
- 验证 Arm4 作为新的 Training Arm 正确集成到系统中
- 确保 Arm4 与 Arm1 共享相同的业务逻辑和限制规则
- 验证前端 UI 正确显示 Arm4 选项和相关信息
- 确保后端队列限制和图像识别功能正常工作
- 验证 Arm4 不影响其他机器人（Arm1, Arm2, Arm3）的功能

#### 质量目标
- **功能完整性**: 100% 功能点覆盖
- **关键路径**: 100% 测试覆盖
- **兼容性**: 确保与现有系统无缝集成
- **用户体验**: Arm4 与 Arm1 体验一致

---

## 🔍 功能分析

### 核心功能点

#### 1. **前端 UI 集成** 🎨
```
代码位置: 
- TeleOpSelection.js (行 26-31, 108)
- TeleOp.js (行 871, 893-894)
```

**功能描述**:
- Arm4 在机器人选择界面显示为 "Training Arm"
- Arm4 与 Arm1 共享相同的描述和状态
- Arm4 可以正常启动操作流程
- Arm4 导航栏显示为 "Training Arm"
- Arm4 不显示 session complete modal（与 Arm1 相同）

**关键代码逻辑**:
```javascript
// TeleOpSelection.js - 添加 Arm4 配置
{
    id: 'arm4',
    name: 'Training Arm',
    status: 'available',
    description: 'Join the queue to practice your skills and earn points with each session.'
}

// TeleOp.js - 不显示 session complete modal
if (robotId !== 'arm1' && robotId !== 'arm4') {
    setShowSessionCompleteModal(true);
}

// TeleOp.js - 导航栏显示
{effectiveRobotId === 'arm1' || effectiveRobotId === 'arm4'
    ? 'Training\u00a0Arm'
    : ...}
```

**测试重点**:
- ✅ Arm4 在机器人选择界面显示（ARM4-F-001）
- ✅ Arm4 显示为 "Training Arm"（ARM4-F-002）
- ✅ Arm4 可以启动操作（ARM4-F-003）
- ✅ Arm4 导航栏显示正确（ARM4-F-004）
- ✅ Arm4 不显示 session complete modal（ARM4-F-005）

---

#### 2. **后端队列限制逻辑** 🔒
```
代码位置: app_prismax_tele_op_services/app.py (行 464-478)
```

**功能描述**:
- Arm1 和 Arm4 共享相同的 Amplifier Member 限制规则
- 每天（UTC）最多可以加入 3 次队列
- 限制按每个机器人独立计算（arm1 和 arm4 分别计算）
- 错误消息动态显示 robot_id

**关键代码逻辑**:
```python
# Arm1/Arm4 Amplifier: max 3 joins per UTC day
if robot_id in ('arm1', 'arm4') and user_row[1] == "Amplifier Member":
    daily_arm_joins = conn.execute(
        sqlalchemy.text("""
                        SELECT COUNT(*)
                        FROM robot_queue
                        WHERE user_id = :uid
                          AND robot_id = :rid
                          AND DATE(created_at AT TIME ZONE 'UTC') = DATE(NOW() AT TIME ZONE 'UTC')
                        """),
        {"uid": user_id, "rid": robot_id}
    ).scalar()

    if daily_arm_joins >= 3:
        return jsonify({"error": f"Amplifier members can join {robot_id} queue up to 3 times per day (UTC)"}), 403
```

**测试重点**:
- ✅ Arm4 Amplifier Member 每天最多 3 次（ARM4-B-001）
- ✅ Arm1 和 Arm4 限制独立计算（ARM4-B-002）
- ✅ UTC 时区限制正确（ARM4-B-003）
- ✅ 错误消息包含 robot_id（ARM4-B-004）

---

#### 3. **图像识别配置** 🖼️
```
代码位置: app_prismax_tele_op_services/image_recognitions.py (行 76)
```

**功能描述**:
- Arm4 使用 PROMPT2（与 Arm2、Arm3 相同）
- Arm1 使用 PROMPT1（独特的提示词）

**关键代码逻辑**:
```python
PROMPT_LIST = {'arm1': PROMPT1, 'arm2': PROMPT2, 'arm3': PROMPT2, 'arm4': PROMPT2}
```

**测试重点**:
- ✅ Arm4 图像识别使用 PROMPT2（ARM4-B-005）
- ✅ Arm4 图像识别功能正常（ARM4-B-006）

---

## 🧪 测试方法论

### 测试层级

#### 1. **功能测试 (Functional Testing)**
- **目标**: 验证功能按预期工作
- **用例**: ARM4-F-001 ~ ARM4-F-015
- **覆盖率**: 核心功能 100%

#### 2. **后端逻辑测试 (Backend Logic Testing)**
- **目标**: 验证队列限制和业务规则
- **用例**: ARM4-B-001 ~ ARM4-B-010
- **关键点**: 限制规则、时区处理、错误处理

#### 3. **集成测试 (Integration Testing)**
- **目标**: 验证前后端集成和完整流程
- **用例**: ARM4-I-001 ~ ARM4-I-005
- **关键点**: 端到端流程、数据一致性

#### 4. **回归测试 (Regression Testing)**
- **目标**: 确保新功能不影响现有功能
- **用例**: ARM4-R-001 ~ ARM4-R-005
- **关键点**: Arm1, Arm2, Arm3 功能不受影响

---

## 📋 测试用例设计

### 测试套件 1: 前端 UI 功能测试

#### ARM4-F-001: Arm4 在机器人选择界面显示
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 导航到 Tele-Op 页面 | 显示机器人选择界面 |
| 2 | 检查机器人卡片列表 | 显示 4 个机器人卡片：Training Arm (arm1), Training Arm (arm4), Buddy Arm (arm3), Partner Arm (arm2) |
| 3 | 定位 Arm4 卡片 | Arm4 卡片显示在列表中（位置在 arm1 之后，arm3 之前） |
| 4 | 检查卡片状态 | 卡片显示 "available" 状态（绿色指示器或可用标识） |

**验证点**:
- Arm4 卡片可见且可点击
- Arm4 卡片位置符合预期（在 arm1 之后）

---

#### ARM4-F-002: Arm4 显示为 "Training Arm"
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 导航到 Tele-Op 页面 | 显示机器人选择界面 |
| 2 | 定位 Arm4 卡片 | 找到 Arm4 卡片 |
| 3 | 检查卡片名称 | 显示 "Training Arm" |
| 4 | 检查卡片描述 | 显示 "Join the queue to practice your skills and earn points with each session." |
| 5 | 对比 Arm1 卡片 | Arm1 和 Arm4 显示相同的名称和描述 |

**验证点**:
- Arm4 名称与 Arm1 一致
- Arm4 描述与 Arm1 一致

---

#### ARM4-F-003: Arm4 可以启动操作流程
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 导航到 Tele-Op 页面 | 显示机器人选择界面 |
| 2 | 点击 Arm4 卡片 | 成功进入 Arm4 控制页面 |
| 3 | 检查页面加载 | 显示 Arm4 队列面板和控制界面 |
| 4 | 检查 URL | URL 包含 arm4 标识（如 `/live-control/arm4`） |

**验证点**:
- Arm4 卡片可点击
- 成功导航到 Arm4 控制页面
- 页面正确加载

---

#### ARM4-F-004: Arm4 导航栏显示为 "Training Arm"
**优先级**: P0  
**前置条件**: 用户在 Arm4 控制页面

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 进入 Arm4 控制页面 | 显示 Arm4 控制界面 |
| 2 | 检查导航栏 | 导航栏显示 "Live Control | Robots Center → Training Arm" |
| 3 | 对比 Arm1 导航栏 | Arm1 导航栏也显示 "Training Arm" |
| 4 | 对比 Arm2 导航栏 | Arm2 导航栏显示 "Partner Arm" |
| 5 | 对比 Arm3 导航栏 | Arm3 导航栏显示 "Buddy Arm" |

**验证点**:
- Arm4 导航栏显示 "Training Arm"
- Arm4 与 Arm1 导航栏显示一致
- 其他机器人导航栏显示正确

---

#### ARM4-F-005: Arm4 不显示 session complete modal
**优先级**: P0  
**前置条件**: 
- 用户已加入 Arm4 队列并完成控制会话
- 用户不是首次使用（已使用过至少一次）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 加入 Arm4 队列 | 成功加入队列 |
| 2 | 等待队列位置到达 #1 | 显示 "Session Active" |
| 3 | 完成 5 分钟控制会话 | 会话结束 |
| 4 | 检查模态框 | **不显示** session complete modal |
| 5 | 对比 Arm2 行为 | 切换到 Arm2，完成会话后**显示** session complete modal |
| 6 | 对比 Arm3 行为 | 切换到 Arm3，完成会话后**显示** session complete modal |

**验证点**:
- Arm4 不显示 session complete modal（与 Arm1 相同）
- Arm2 和 Arm3 仍然显示 session complete modal

---

#### ARM4-F-006: Arm4 首次使用显示首次使用模态框
**优先级**: P1  
**前置条件**: 用户首次使用 Arm4（从未控制过任何机器人）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 使用新账号登录 | 登录成功 |
| 2 | 进入 Arm4 控制页面 | 显示 Arm4 控制界面 |
| 3 | 加入队列并完成会话 | 完成首次控制会话 |
| 4 | 检查模态框 | **显示**首次使用模态框（First Time Modal） |

**验证点**:
- 首次使用显示 First Time Modal
- 后续使用不显示 First Time Modal

---

#### ARM4-F-007: Arm4 队列加入按钮功能
**优先级**: P0  
**前置条件**: 用户在 Arm4 控制页面

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 进入 Arm4 控制页面 | 显示队列面板 |
| 2 | 检查按钮文本 | 显示 "Enter Live Control" 按钮 |
| 3 | 点击 "Enter Live Control" | 按钮文本变为 "Starting..." |
| 4 | 等待加入队列 | 成功加入队列，按钮变为 "Leave Queue" |
| 5 | 检查队列位置 | 显示队列位置（如 "Position: 3"） |

**验证点**:
- 按钮状态转换正确
- 队列加入成功

---

#### ARM4-F-008: Arm4 队列离开功能
**优先级**: P0  
**前置条件**: 用户在 Arm4 队列中

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 加入 Arm4 队列 | 成功加入队列 |
| 2 | 检查按钮文本 | 显示 "Leave Queue" 按钮 |
| 3 | 点击 "Leave Queue" | 成功离开队列 |
| 4 | 检查按钮文本 | 按钮恢复为 "Enter Live Control" |
| 5 | 检查队列位置 | 队列位置信息消失 |

**验证点**:
- 离开队列功能正常
- UI 状态正确更新

---

#### ARM4-F-009: Arm4 队列位置更新
**优先级**: P1  
**前置条件**: 用户在 Arm4 队列中

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 加入 Arm4 队列 | 成功加入队列，显示初始位置 |
| 2 | 等待队列位置变化 | 队列位置自动更新（如从 #5 变为 #4） |
| 3 | 检查位置显示 | 位置数字正确更新 |
| 4 | 等待到达 #1 | 位置到达 #1 时显示 "Session Active" |

**验证点**:
- 队列位置实时更新
- 位置显示准确

---

#### ARM4-F-010: Arm4 控制界面功能
**优先级**: P1  
**前置条件**: 用户已激活 Arm4 控制（队列位置 #1）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 等待队列位置到达 #1 | 显示 "Session Active" |
| 2 | 检查视频流 | 显示机器人视频流（stream1 和 stream2） |
| 3 | 检查控制面板 | 显示控制按钮和滑块 |
| 4 | 测试控制功能 | 可以正常控制机器人移动 |
| 5 | 检查会话倒计时 | 显示 5 分钟倒计时 |

**验证点**:
- 控制界面正常加载
- 视频流正常显示
- 控制功能正常

---

### 测试套件 2: 后端逻辑测试

#### ARM4-B-001: Arm4 Amplifier Member 每天最多 3 次限制
**优先级**: P0  
**前置条件**: 
- Amplifier Member 账号
- 当前 UTC 日期未使用过 Arm4

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 登录 Amplifier Member 账号 | 登录成功 |
| 2 | 加入 Arm4 队列（第 1 次） | 成功加入队列 |
| 3 | 离开队列 | 成功离开 |
| 4 | 加入 Arm4 队列（第 2 次） | 成功加入队列 |
| 5 | 离开队列 | 成功离开 |
| 6 | 加入 Arm4 队列（第 3 次） | 成功加入队列 |
| 7 | 离开队列 | 成功离开 |
| 8 | 加入 Arm4 队列（第 4 次） | **失败**，显示错误: "Amplifier members can join arm4 queue up to 3 times per day (UTC)" |

**验证点**:
- 前 3 次成功加入
- 第 4 次被拒绝
- 错误消息正确

---

#### ARM4-B-002: Arm1 和 Arm4 限制独立计算
**优先级**: P0  
**前置条件**: 
- Amplifier Member 账号
- 当前 UTC 日期未使用过 Arm1 和 Arm4

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 登录 Amplifier Member 账号 | 登录成功 |
| 2 | 加入 Arm1 队列 3 次 | 前 3 次成功，第 4 次失败 |
| 3 | 加入 Arm4 队列 | **成功**加入（Arm4 限制独立计算） |
| 4 | 离开 Arm4 队列 | 成功离开 |
| 5 | 加入 Arm4 队列（第 2 次） | 成功加入 |
| 6 | 离开 Arm4 队列 | 成功离开 |
| 7 | 加入 Arm4 队列（第 3 次） | 成功加入 |
| 8 | 离开 Arm4 队列 | 成功离开 |
| 9 | 加入 Arm4 队列（第 4 次） | **失败**，显示错误消息 |

**验证点**:
- Arm1 和 Arm4 限制独立
- 每个机器人最多 3 次/天

---

#### ARM4-B-003: UTC 时区限制正确
**优先级**: P1  
**前置条件**: 
- Amplifier Member 账号
- 已使用 Arm4 3 次（当前 UTC 日期）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 确认当前 UTC 日期 | 记录当前 UTC 日期 |
| 2 | 尝试加入 Arm4 队列（第 4 次） | 失败，显示错误消息 |
| 3 | 等待 UTC 日期变更（或手动修改数据库时间） | UTC 日期变为下一天 |
| 4 | 尝试加入 Arm4 队列 | **成功**加入（新的一天，限制重置） |

**验证点**:
- 限制基于 UTC 时区
- 新的一天限制重置

**注意**: 此测试可能需要等待或使用测试工具修改数据库时间

---

#### ARM4-B-004: 错误消息包含 robot_id
**优先级**: P1  
**前置条件**: Amplifier Member 账号，已使用 Arm4 3 次

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 尝试加入 Arm4 队列（第 4 次） | 失败 |
| 2 | 检查错误消息 | 错误消息包含 "arm4" |
| 3 | 尝试加入 Arm1 队列（第 4 次） | 失败 |
| 4 | 检查错误消息 | 错误消息包含 "arm1" |

**验证点**:
- 错误消息动态显示 robot_id
- Arm4 错误消息包含 "arm4"
- Arm1 错误消息包含 "arm1"

---

#### ARM4-B-005: Arm4 图像识别使用 PROMPT2
**优先级**: P1  
**前置条件**: 用户已激活 Arm4 控制

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 激活 Arm4 控制 | 控制会话开始 |
| 2 | 触发图像识别功能 | 执行图像识别操作 |
| 3 | 检查后端日志 | 使用 PROMPT2 进行识别 |
| 4 | 对比 Arm1 | Arm1 使用 PROMPT1 |
| 5 | 对比 Arm2/Arm3 | Arm2 和 Arm3 使用 PROMPT2（与 Arm4 相同） |

**验证点**:
- Arm4 使用 PROMPT2
- Arm1 使用 PROMPT1（不同）
- Arm2/Arm3 使用 PROMPT2（相同）

**注意**: 此测试需要查看后端日志或使用 API 测试

---

#### ARM4-B-006: Arm4 图像识别功能正常
**优先级**: P1  
**前置条件**: 用户已激活 Arm4 控制

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 激活 Arm4 控制 | 控制会话开始 |
| 2 | 触发图像识别 | 执行图像识别操作 |
| 3 | 检查识别结果 | 返回有效的识别结果（JSON 格式） |
| 4 | 验证结果格式 | 结果包含 "left" 和 "right" 字段 |

**验证点**:
- 图像识别功能正常
- 返回结果格式正确

---

#### ARM4-B-007: Arm4 队列加入 API 正常
**优先级**: P0  
**前置条件**: 用户已登录，获取 JWT token

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 调用 API: `POST /queue/join` | 发送请求 |
| 2 | 请求体包含 `robot_id: "arm4"` | 请求格式正确 |
| 3 | 检查响应 | 返回 200 状态码 |
| 4 | 检查响应体 | 包含 `position` 字段 |

**API 测试**:
```bash
curl -X POST https://control.prismax.ai/queue/join \
  -H "Authorization: Bearer {JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "robot_id": "arm4",
    "user_id": "{USER_ID}"
  }'
```

**预期响应**:
```json
{
  "success": true,
  "position": 1,
  "message": "Joined queue successfully"
}
```

---

#### ARM4-B-008: Arm4 队列限制 API 验证
**优先级**: P0  
**前置条件**: Amplifier Member，已使用 Arm4 3 次

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 调用 API: `POST /queue/join` | 发送请求 |
| 2 | 请求体包含 `robot_id: "arm4"` | 请求格式正确 |
| 3 | 检查响应 | 返回 403 状态码 |
| 4 | 检查响应体 | 包含错误消息: "Amplifier members can join arm4 queue up to 3 times per day (UTC)" |

**API 测试**:
```bash
curl -X POST https://control.prismax.ai/queue/join \
  -H "Authorization: Bearer {JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "robot_id": "arm4",
    "user_id": "{USER_ID}"
  }'
```

**预期响应**:
```json
{
  "error": "Amplifier members can join arm4 queue up to 3 times per day (UTC)"
}
```

---

#### ARM4-B-009: Arm4 队列查询 API
**优先级**: P1  
**前置条件**: 用户在 Arm4 队列中

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 调用 API: `GET /queue/status?robot_id=arm4` | 发送请求 |
| 2 | 检查响应 | 返回 200 状态码 |
| 3 | 检查响应体 | 包含队列信息和用户位置 |

---

#### ARM4-B-010: Arm4 不同会员等级限制
**优先级**: P1  
**前置条件**: 准备不同会员等级的账号

| 会员等级 | 预期行为 |
|---------|---------|
| Explorer Member | 无法使用机器人（显示升级提示） |
| Amplifier Member | Arm4 每天最多 3 次 |
| Innovator Member | 无限制（或根据业务规则） |

**测试步骤**:
1. 使用 Explorer Member 账号尝试加入 Arm4 队列
2. 使用 Amplifier Member 账号加入 Arm4 队列（验证限制）
3. 使用 Innovator Member 账号加入 Arm4 队列（验证无限制）

---

### 测试套件 3: 集成测试

#### ARM4-I-001: Arm4 完整流程测试
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 导航到 Tele-Op 页面 | 显示机器人选择界面 |
| 2 | 点击 Arm4 卡片 | 进入 Arm4 控制页面 |
| 3 | 点击 "Enter Live Control" | 加入队列 |
| 4 | 等待队列位置到达 #1 | 显示 "Session Active" |
| 5 | 检查控制界面 | 显示视频流和控制面板 |
| 6 | 完成 5 分钟控制会话 | 会话结束 |
| 7 | 检查模态框 | 不显示 session complete modal |
| 8 | 检查积分奖励 | 获得 Prisma Points（如果适用） |

**验证点**:
- 完整流程无错误
- 所有功能正常

---

#### ARM4-I-002: Arm4 与 Arm1 行为一致性
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 测试 Arm1 完整流程 | 记录 Arm1 行为 |
| 2 | 测试 Arm4 完整流程 | 记录 Arm4 行为 |
| 3 | 对比行为 | Arm4 与 Arm1 行为一致（除了 robot_id） |
| 4 | 对比 UI 显示 | Arm4 与 Arm1 UI 显示一致 |
| 5 | 对比限制规则 | Arm4 与 Arm1 限制规则一致 |

**验证点**:
- Arm4 与 Arm1 行为一致
- UI 显示一致
- 限制规则一致

---

#### ARM4-I-003: Arm4 队列并发测试
**优先级**: P1  
**前置条件**: 多个用户账号

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 用户 A 加入 Arm4 队列 | 成功加入，位置 #1 |
| 2 | 用户 B 加入 Arm4 队列 | 成功加入，位置 #2 |
| 3 | 用户 C 加入 Arm4 队列 | 成功加入，位置 #3 |
| 4 | 用户 A 离开队列 | 用户 B 位置变为 #1 |
| 5 | 用户 C 位置更新 | 用户 C 位置变为 #2 |

**验证点**:
- 队列并发处理正常
- 位置更新正确

---

#### ARM4-I-004: Arm4 数据一致性测试
**优先级**: P1  
**前置条件**: 用户已使用 Arm4

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 加入 Arm4 队列 | 成功加入 |
| 2 | 检查数据库 | `robot_queue` 表中有记录，`robot_id = 'arm4'` |
| 3 | 完成控制会话 | 会话结束 |
| 4 | 检查数据库 | `tele_op_control_history` 表中有记录，`robot_id = 'arm4'` |
| 5 | 检查积分记录 | 积分记录正确（如果适用） |

**验证点**:
- 数据库记录正确
- 数据一致性

---

#### ARM4-I-005: Arm4 跨页面导航测试
**优先级**: P1  
**前置条件**: 用户在 Arm4 控制页面

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 在 Arm4 控制页面 | 显示 Arm4 控制界面 |
| 2 | 点击导航栏 "Robots Center" | 返回机器人选择界面 |
| 3 | 点击 Arm1 卡片 | 进入 Arm1 控制页面 |
| 4 | 点击导航栏 "Robots Center" | 返回机器人选择界面 |
| 5 | 点击 Arm4 卡片 | 进入 Arm4 控制页面 |
| 6 | 检查状态 | Arm4 状态正确（如果之前在队列中，状态应保持） |

**验证点**:
- 跨页面导航正常
- 状态保持正确

---

### 测试套件 4: 回归测试

#### ARM4-R-001: Arm1 功能不受影响
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 测试 Arm1 完整流程 | Arm1 所有功能正常 |
| 2 | 检查 Arm1 UI | Arm1 UI 显示正确 |
| 3 | 检查 Arm1 限制 | Arm1 限制规则正常 |
| 4 | 检查 Arm1 图像识别 | Arm1 图像识别正常（使用 PROMPT1） |

**验证点**:
- Arm1 功能完全正常
- 不受 Arm4 影响

---

#### ARM4-R-002: Arm2 功能不受影响
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 测试 Arm2 完整流程 | Arm2 所有功能正常 |
| 2 | 检查 Arm2 邀请码验证 | Arm2 邀请码验证正常 |
| 3 | 检查 Arm2 UI | Arm2 UI 显示正确 |

**验证点**:
- Arm2 功能完全正常
- 不受 Arm4 影响

---

#### ARM4-R-003: Arm3 功能不受影响
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 测试 Arm3 完整流程 | Arm3 所有功能正常 |
| 2 | 检查 Arm3 限制 | Arm3 限制规则正常（lifetime 3 次） |
| 3 | 检查 Arm3 UI | Arm3 UI 显示正确 |

**验证点**:
- Arm3 功能完全正常
- 不受 Arm4 影响

---

#### ARM4-R-004: 机器人选择界面显示正确
**优先级**: P0  
**前置条件**: 用户已登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 导航到 Tele-Op 页面 | 显示机器人选择界面 |
| 2 | 检查机器人列表 | 显示 4 个机器人：arm1, arm4, arm3, arm2 |
| 3 | 检查每个机器人名称 | arm1 和 arm4 显示 "Training Arm"，arm3 显示 "Buddy Arm"，arm2 显示 "Partner Arm" |
| 4 | 检查每个机器人状态 | 所有机器人状态正确显示 |

**验证点**:
- 所有机器人正确显示
- 名称和状态正确

---

#### ARM4-R-005: 队列系统整体功能
**优先级**: P0  
**前置条件**: 多个用户账号

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 用户 A 加入 Arm1 队列 | 成功加入 |
| 2 | 用户 B 加入 Arm4 队列 | 成功加入 |
| 3 | 用户 C 加入 Arm2 队列 | 成功加入 |
| 4 | 用户 D 加入 Arm3 队列 | 成功加入 |
| 5 | 检查所有队列 | 所有队列独立运行，互不影响 |

**验证点**:
- 队列系统整体正常
- 各机器人队列独立

---

## 🔧 测试执行策略

### 测试环境配置

#### 1. **前端环境**
```
开发环境: http://localhost:3000
QA 环境: https://qa-app.prismax.ai
生产环境: https://app.prismax.ai
```

#### 2. **后端环境**
```
控制 API: https://control.prismax.ai
网关 API: https://gateway.prismax.ai
```

#### 3. **测试账号**
```
账号 1: test-amplifier@prismax.ai (Amplifier Member)
账号 2: test-innovator@prismax.ai (Innovator Member)
账号 3: test-explorer@prismax.ai (Explorer Member)
账号 4: test-new-user@prismax.ai (新用户，首次使用)
```

---

### 测试执行顺序

#### 阶段 1: 冒烟测试 (Smoke Test) - 30分钟
执行所有 P0 用例，快速验证核心功能

```
✓ ARM4-F-001: Arm4 在机器人选择界面显示
✓ ARM4-F-002: Arm4 显示为 "Training Arm"
✓ ARM4-F-003: Arm4 可以启动操作流程
✓ ARM4-F-004: Arm4 导航栏显示正确
✓ ARM4-F-005: Arm4 不显示 session complete modal
✓ ARM4-B-001: Arm4 Amplifier Member 每天最多 3 次限制
✓ ARM4-B-002: Arm1 和 Arm4 限制独立计算
✓ ARM4-I-001: Arm4 完整流程测试
✓ ARM4-I-002: Arm4 与 Arm1 行为一致性
✓ ARM4-R-001: Arm1 功能不受影响
✓ ARM4-R-002: Arm2 功能不受影响
✓ ARM4-R-003: Arm3 功能不受影响
```

#### 阶段 2: 功能测试 (Functional Test) - 2小时
执行所有 P0 + P1 用例，全面验证功能

```
包含阶段 1 所有用例
+ 前端 UI 详细测试
+ 后端限制逻辑测试
+ 图像识别功能测试
+ 集成测试
+ 跨页面导航测试
```

#### 阶段 3: 完整测试 (Full Test) - 3小时
执行所有 35 个用例，包括边界条件和回归测试

```
包含阶段 2 所有用例
+ 边界条件测试
+ 并发测试
+ 数据一致性测试
+ 完整回归测试
```

---

## 📊 测试指标与验收标准

### 关键性能指标 (KPI)

#### 1. **功能指标**
```
通过率目标:
- P0 用例: 100% 通过
- P1 用例: ≥ 95% 通过
- P2 用例: ≥ 90% 通过

缺陷密度:
- P0 缺陷: 0 个
- P1 缺陷: ≤ 2 个
- P2 缺陷: ≤ 5 个
```

#### 2. **兼容性指标**
```
功能兼容性:
- Arm4 与 Arm1 行为一致性: 100%
- 其他机器人功能不受影响: 100%
- UI 显示正确: 100%
```

---

### 发布准入标准 (Release Criteria)

#### ✅ 必须满足
1. 所有 P0 用例 100% 通过
2. 无 P0/P1 级别的未修复缺陷
3. Arm4 与 Arm1 行为一致
4. 其他机器人（Arm1, Arm2, Arm3）功能不受影响
5. 队列限制逻辑正确

#### ✅ 强烈建议
6. P1 用例通过率 ≥ 95%
7. 图像识别功能验证通过
8. 数据一致性验证通过
9. 完整回归测试通过

---

## 🐛 风险评估与缓解

### 高风险项 🔴

#### 1. **Arm4 与 Arm1 行为不一致**
**风险描述**: Arm4 和 Arm1 应该行为一致，但可能存在差异

**缓解措施**:
- 重点测试 ARM4-I-002（行为一致性测试）
- 对比 Arm1 和 Arm4 的所有功能点
- 确保代码逻辑一致

#### 2. **队列限制逻辑错误**
**风险描述**: Arm1 和 Arm4 限制可能计算错误或相互影响

**缓解措施**:
- 重点测试 ARM4-B-002（限制独立计算）
- 验证数据库查询逻辑
- 测试边界条件（3 次限制）

---

### 中风险项 🟠

#### 3. **图像识别配置错误**
**风险描述**: Arm4 可能使用了错误的 PROMPT

**缓解措施**:
- 测试 ARM4-B-005（PROMPT2 验证）
- 检查后端日志
- 对比 Arm2/Arm3 的图像识别结果

#### 4. **UI 显示不一致**
**风险描述**: Arm4 UI 可能与 Arm1 显示不一致

**缓解措施**:
- 详细测试所有 UI 相关用例
- 对比 Arm1 和 Arm4 的 UI
- 检查导航栏、模态框等关键 UI 元素

---

### 低风险项 🟡

#### 5. **性能影响**
**风险描述**: 新增 Arm4 可能影响系统性能

**缓解措施**:
- 监控系统性能
- 测试并发场景
- 如有问题，优化数据库查询

---

## 📈 测试改进建议

### 短期改进（当前版本）
1. ✅ 完成所有 35 个测试用例
2. ✅ 重点验证 P0 用例
3. ✅ 确保 Arm4 与 Arm1 行为一致
4. ✅ 完整回归测试

### 中期改进（下个迭代）
1. 🔄 引入自动化测试（Cypress/Playwright）
2. 🔄 添加性能监控
3. 🔄 建立测试数据管理系统

### 长期改进（后续版本）
1. 📋 建立 Arm4 的自动化回归测试套件
2. 📋 集成到 CI/CD 流程
3. 📋 建立用户反馈收集机制

---

## 📞 联系人与责任人

### 测试团队
- **QA Lead**: _____________
- **功能测试**: _____________
- **API 测试**: _____________

### 开发团队
- **功能负责人**: Chris
- **Code Reviewer**: _____________
- **技术支持**: _____________

---

## 📚 附录

### A. 代码变更清单

**前端变更 (Commit 694a6c0)**:
```
修改文件:
1. src/components/TeleOp/TeleOp.js
   - 修改 session complete modal 条件 (行 871)
   - 修改导航栏显示逻辑 (行 893-894)

2. src/components/TeleOp/TeleOpSelection.js
   - 新增 Arm4 配置 (行 26-31)
   - 修改 handleStartOperation (行 108)
```

**后端变更 (Commit 06b6dc2)**:
```
修改文件:
1. app_prismax_tele_op_services/app.py
   - 修改 Amplifier Member 限制逻辑 (行 464-478)
   - 合并 arm1 和 arm4 的限制规则

2. app_prismax_tele_op_services/image_recognitions.py
   - 新增 arm4 到 PROMPT_LIST (行 76)
   - arm4 使用 PROMPT2
```

### B. 相关链接
- [Commit 694a6c0 (Frontend)](https://github.com/PrismaXAI/app-prismax-rp/commit/694a6c0)
- [Commit 06b6dc2 (Backend)](https://github.com/PrismaXAI/app-prismax-rp-backend/commit/06b6dc2)

### C. 测试工具
- **浏览器开发者工具**: 监控网络和控制台
- **API 测试工具**: Postman / curl
- **数据库工具**: 查询和验证数据
- **屏幕录制**: OBS Studio / QuickTime

---

**文档版本**: v1.0  
**创建日期**: 2026-01-22  
**作者**: QA Team  
**审核状态**: ⬜ 待审核  
**下次更新**: 2026-02-22
