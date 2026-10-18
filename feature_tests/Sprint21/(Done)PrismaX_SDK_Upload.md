# PrismaX SDK Upload QA Guide

## 一、文档目的

本文说明如何使用 `prismax-0.1.3` Python SDK 上传 PrismaX episode 数据，并提供完整 E2E 测试用例，用于验证 SDK 的本地校验、上传、状态查询、resume、权限和异常处理能力。

历史本地源码包已经移除。如需复现该版本，请安装已发布的 `0.1.3` 包：

```bash
python -m pip install "prismax==0.1.3"
```

适用对象：

- QA 验证 SDK 上传链路
- Operator 用户验证 Upload API key
- 开发/测试人员复现上传、失败、resume、wait 等场景

---

## 二、SDK 能做什么

`prismax-0.1.3` 是 PrismaX 数据上传 SDK，核心能力包括：

| 功能 | 说明 |
|---|---|
| 本地扫描数据目录 | 扫描 `.mcap` 和 `.mp4` 文件，忽略隐藏文件和已有 `_MANIFEST.json` |
| 本地结构校验 | 校验每个 episode 是否有 1 个 `.mcap` 和至少 3 个 `.mp4` |
| primary video 识别 | 根据文件名识别 env/high、left、right 三路 primary video |
| task 解析 | 支持传 `task_id`，也支持传 `scenario/task_name` 自动解析 task |
| 创建 upload session | 调用 PrismaX data pipeline 创建上传会话 |
| 上传 raw 文件 | 使用 signed URL 并发上传本地 raw 文件 |
| 上传 manifest | raw 文件上传后，最后上传 `{episode}/_MANIFEST.json` 触发 worker |
| 查询状态 | 支持 `prismax status <upload_id>` |
| 等待处理完成 | 支持 `--wait`，轮询到 terminal status |
| 恢复上传 | 支持 `prismax resume <upload_id> <original_folder>` |

---

## 三、上传前准备

## 3.1 安装 SDK

安装历史 SDK 版本：

```bash
python -m pip install "prismax==0.1.3"
```

安装后确认 CLI 可用：

```bash
prismax --help
```

## 3.2 准备 Upload API key

在 PrismaX App 创建 Operator / Upload key：

```text
Account Page -> API Keys -> Operator -> New key
```

要求：

- key 前缀应为 `pxu_`
- Subscriber / Download key 不能用于上传
- key 只在创建时展示一次，需要立即复制保存

设置环境变量：

```bash
export PRISMAX_API_KEY="pxu_your_upload_api_key"
```

也可以在命令中显式传入：

```bash
prismax upload ./data --task-id 12 --serial-number robot_serial_number --api-key pxu_your_upload_api_key
```

## 3.3 准备 task 与 robot serial number

上传必须提供：

| 字段 | 说明 |
|---|---|
| `task_id` | 数字 task ID，推荐用于 QA 稳定测试 |
| `scenario` / `task_name` | task 场景名，SDK 会调用 `/data/tasks` 做大小写不敏感的精确匹配 |
| `serial_number` | 注册在当前 operator 账号下的 robot serial number |

推荐 QA 使用 `task_id`，避免 scenario 重名或文案变化导致误判。

---

## 四、数据目录规范

## 4.1 单 episode 示例

```text
data/
  1.mcap
  1/
    high.mp4
    left.mp4
    right.mp4
```

## 4.2 多 episode 示例

```text
data/
  1.mcap
  1/
    high.mp4
    left.mp4
    right.mp4
  2.mcap
  2/
    high.mp4
    left.mp4
    right.mp4
```

## 4.3 支持 additional videos

```text
data/
  1.mcap
  1/
    high.mp4
    left.mp4
    right.mp4
    high2.mp4
    left2.mp4
    right2.mp4
```

primary video 选择规则：

| Slot | 识别规则 | exact name 优先 |
|---|---|---|
| env/high | 文件名不包含 `left` / `right` | `high.mp4`, `env.mp4` |
| left | 文件名包含 `left` | `left.mp4` |
| right | 文件名包含 `right` | `right.mp4` |

例如同时存在 `left.mp4` 与 `left2.mp4` 时，SDK 会优先选择 `left.mp4` 作为 primary left video。

## 4.4 不支持/会被拒绝的结构

| 场景 | 结果 |
|---|---|
| root 下放非 `.mcap` 文件 | 本地校验失败 |
| episode 文件夹下放非 `.mp4` 文件 | 本地校验失败 |
| `.MP4` 大写扩展名 | 本地校验失败 |
| episode 下存在嵌套目录 | 本地校验失败 |
| 缺少 `{episode}.mcap` | 本地校验失败 |
| 少于 3 个 `.mp4` | 本地校验失败 |
| 缺少 left/right/env 任一 primary slot | 本地校验失败 |
| 隐藏文件，如 `.DS_Store`、`._left.mp4` | 自动忽略 |
| 已有 `_MANIFEST.json` | 自动忽略，由 SDK 重新生成 |

---

## 五、CLI 上传方式

## 5.1 使用 task_id 上传

```bash
prismax upload ./data \
  --task-id 12 \
  --serial-number robot_serial_number
```

成功后输出类似：

```text
Upload ID: 123
Status: UPLOADING
Episodes: 2
Serial number: robot_serial_number
Created at: ...
```

## 5.2 使用 scenario 上传

```bash
prismax upload ./data \
  --scenario "Pick and place packaged food items" \
  --serial-number robot_serial_number
```

注意：

- scenario 是标准化后的精确匹配，不是模糊搜索。
- 如果匹配不到，会报 `No task found...`。
- 如果匹配多个，会要求改用 `task_id`。

## 5.3 上传并等待 worker 完成

```bash
prismax upload ./data \
  --task-id 12 \
  --serial-number robot_serial_number \
  --wait
```

默认等待：

| 参数 | 默认值 |
|---|---:|
| `--max-wait` | 1800 秒 |
| `--poll-interval` | 10 秒 |
| `--max-poll-errors` | 3 次 |

自定义：

```bash
prismax upload ./data \
  --task-id 12 \
  --serial-number robot_serial_number \
  --wait \
  --max-wait 3600 \
  --poll-interval 5 \
  --max-poll-errors 3
```

SDK 认为以下状态是 terminal status：

```text
DERIVED_READY
DERIVED_VALIDATION_FAILED
FAILED
DERIVED_PARTIALLY_READY
```

## 5.4 输出完整 JSON

```bash
prismax upload ./data \
  --task-id 12 \
  --serial-number robot_serial_number \
  --json
```

## 5.5 查询状态

```bash
prismax status 123
```

完整 JSON：

```bash
prismax status 123 --json
```

## 5.6 Resume 上传

如果上传 raw file 过程中失败，SDK 会提示类似：

```text
Resume with: prismax resume 123 ./data
```

执行：

```bash
prismax resume 123 ./data
```

重要限制：

- 必须传**原始完整 data folder**。
- 不要只传失败文件或剩余文件。
- resume 仅适用于 upload 仍处于 `UPLOADING` 阶段。
- 一旦进入 worker processing 或 terminal status，应该重新创建 upload。

---

## 六、Python API 上传方式

## 6.1 基本上传

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=12,
    serial_number="robot_serial_number",
)

print(result["upload_id"])
```

## 6.2 使用 scenario

```python
import prismax

result = prismax.upload(
    "./data",
    scenario="Pick and place packaged food items",
    serial_number="robot_serial_number",
)
```

## 6.3 直接传 API key

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=12,
    serial_number="robot_serial_number",
    api_key="pxu_your_upload_api_key",
)
```

## 6.4 等待完成

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=12,
    serial_number="robot_serial_number",
    wait=True,
    max_wait=3600,
    poll_interval=5,
)

print(result["status"])
```

## 6.5 查询状态

```python
import prismax

status = prismax.status(123)
print(status)
```

## 6.6 Resume

```python
import prismax

result = prismax.resume(
    123,
    "./data",
)
```

## 6.7 错误处理

```python
import prismax

try:
    prismax.upload(
        "./data",
        task_id=12,
        serial_number="robot_serial_number",
    )
except prismax.PrismaxValidationError as exc:
    print(f"Invalid upload folder: {exc}")
except prismax.PrismaxAuthError as exc:
    print(f"API key or permission error: {exc}")
except prismax.PrismaxApiError as exc:
    print(f"PrismaX API error: {exc}")
```

---

## 七、SDK 上传链路

```text
本地 data folder
  ↓
scan_folder()
  ↓
validate_mcap_mp4()
  ↓
resolve_task_id()
  ↓
POST /v1/data/upload-sessions
  ↓
并发 PUT raw files 到 signed URLs
  ↓
为每个 episode 生成 _MANIFEST.json
  ↓
PUT manifest 到 signed URL
  ↓
后端 worker 被 manifest 触发
  ↓
status / wait 查询处理结果
```

---

## 八、E2E 测试用例

| Case ID | 模块 | 测试场景 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|---|
| SDK-E2E-001 | 安装 | 本地源码安装 SDK | 本机 Python >= 3.9；在 `prismax-0.1.3` 目录 | 1. 执行 `python -m pip install .`；2. 执行 `prismax --help` | 安装成功；CLI 可用；help 显示 `upload/resume/status` 子命令 | P0 |
| SDK-E2E-002 | API Key | 使用环境变量读取 upload key | 已设置有效 `PRISMAX_API_KEY=pxu_...` | 1. 不传 `--api-key` 执行上传命令 | SDK 使用环境变量认证；不会报 `api_key is required` | P0 |
| SDK-E2E-003 | API Key | 缺少 API key | 未设置 `PRISMAX_API_KEY`，命令也不传 `--api-key` | 1. 执行 `prismax status 123` | 返回错误；提示 `api_key is required or PRISMAX_API_KEY must be set.` | P0 |
| SDK-E2E-004 | API Key | 使用 Subscriber/Download key 上传 | 准备非 `pxu_` 或无 upload 权限的 key | 1. 执行 upload 命令 | 后端拒绝；SDK 抛 `PrismaxAuthError` 或 CLI 返回非 0；不创建有效上传 | P0 |
| SDK-E2E-005 | 本地校验 | 上传合法单 episode | data folder 含 `1.mcap`、`1/high.mp4`、`1/left.mp4`、`1/right.mp4` | 1. 执行 `prismax upload ./data --task-id <id> --serial-number <sn>` | 本地校验通过；创建 upload session；raw 文件与 manifest 上传成功；返回 upload ID | P0 |
| SDK-E2E-006 | 本地校验 | 上传合法多 episode | data folder 含 `1`、`2` 两组合法 episode | 1. 执行 upload | 返回 `episode_count=2` 或对应上传摘要；每个 episode 都生成并上传 manifest | P0 |
| SDK-E2E-007 | 本地校验 | additional videos 可上传 | episode 中除 primary 三路外还有 `high2.mp4/left2.mp4/right2.mp4` | 1. 执行 upload；2. 查询 upload/后端文件记录 | 本地校验通过；additional videos 进入 manifest；不阻断上传 | P0 |
| SDK-E2E-008 | 本地校验 | 缺少 `.mcap` | data folder 只有 `1/high.mp4`、`1/left.mp4`、`1/right.mp4` | 1. 执行 upload | 本地失败；提示 episode must have exactly 1 `.mcap`；不调用 upload session | P0 |
| SDK-E2E-009 | 本地校验 | 缺少 primary right video | data folder 有 `.mcap`、`high.mp4`、`left.mp4`、`left2.mp4` | 1. 执行 upload | 本地失败；提示 missing `right`；不调用 upload session | P0 |
| SDK-E2E-010 | 本地校验 | 少于 3 个 MP4 | episode 下只有 2 个 `.mp4` | 1. 执行 upload | 本地失败；提示 at least 3 `.mp4` files | P0 |
| SDK-E2E-011 | 本地校验 | 大写 `.MP4` 被拒绝 | episode 下有 `left.MP4` | 1. 执行 upload | 本地失败；提示 only `.mp4` files are allowed | P0 |
| SDK-E2E-012 | 本地校验 | 嵌套文件夹被拒绝 | episode 下有 `1/nested/left.mp4` | 1. 执行 upload | 本地失败；提示 nested folders are not allowed | P0 |
| SDK-E2E-013 | 本地校验 | 隐藏文件被忽略 | data folder 有 `.DS_Store`、`1/._left.mp4` | 1. 执行 upload | 隐藏文件不进入 files payload；上传不受影响 | P1 |
| SDK-E2E-014 | 本地校验 | 已有 `_MANIFEST.json` 被忽略 | data folder 已存在 `1/_MANIFEST.json` | 1. 执行 upload | 本地已有 manifest 不上传；SDK 重新生成 manifest placeholder 和 payload | P1 |
| SDK-E2E-015 | Primary 选择 | exact primary name 优先 | 同时存在 `high.mp4/high2.mp4/left.mp4/left2.mp4/right.mp4/right2.mp4` | 1. 执行 upload；2. 检查后端 derived/QA 使用的 primary | primary 应选择 `high.mp4`、`left.mp4`、`right.mp4` | P1 |
| SDK-E2E-016 | Task 解析 | 使用 `task_id` 上传 | 已知有效 task ID | 1. 执行 `prismax upload ./data --task-id <id> --serial-number <sn>` | SDK 不需要 `/data/tasks` name 匹配；直接使用该 task ID 创建 session | P0 |
| SDK-E2E-017 | Task 解析 | 使用 scenario 上传 | scenario 与后端 task 名精确匹配 | 1. 执行 `prismax upload ./data --scenario "<scenario>" --serial-number <sn>` | SDK 调用 `/data/tasks` 并解析到唯一 task ID；上传成功 | P1 |
| SDK-E2E-018 | Task 解析 | scenario 不存在 | 使用不存在的 scenario | 1. 执行 upload | SDK 抛 `PrismaxValidationError`；提示 No task found，并列出部分可用 tasks | P1 |
| SDK-E2E-019 | Task 解析 | scenario 匹配多个 task | 构造/选择会匹配多个 task 的名称 | 1. 执行 upload | SDK 抛 `PrismaxValidationError`；提示 Multiple tasks matched，要求使用 task_id | P2 |
| SDK-E2E-020 | Serial Number | 缺少 serial number | 不传 `--serial-number` | 1. 执行 CLI upload | CLI 参数校验失败或 SDK 抛 `serial_number is required` | P0 |
| SDK-E2E-021 | Serial Number | serial number 无权限 | 使用不属于当前 operator 的 serial number | 1. 执行 upload | 后端拒绝创建 session；SDK 返回 auth/api error；不会上传文件 | P0 |
| SDK-E2E-022 | Upload Session | files payload 包含 manifest placeholder | 使用 mock 或抓包 | 1. 执行 upload；2. 检查 `POST /v1/data/upload-sessions` body | body 中包含 raw files 与 `{episode}/_MANIFEST.json` placeholder | P1 |
| SDK-E2E-023 | Raw Upload | signed URL raw 文件并发上传 | upload session 返回多个 signed URL | 1. 执行 upload；2. 观察 storage/请求日志 | raw `.mcap` 和 `.mp4` 均 PUT 到 signed URL；content-type 正确 | P0 |
| SDK-E2E-024 | Manifest Upload | manifest 最后上传 | upload session 正常返回 signed URLs | 1. 执行 upload；2. 检查 manifest 内容 | raw 文件先上传；manifest 后上传；manifest 包含 `upload_id`、`episode_key`、`machine_id`、`task_id`、`files` | P0 |
| SDK-E2E-025 | Wait | 上传并等待 DERIVED_READY | 准备可成功处理的数据 | 1. 执行 upload `--wait` | SDK 轮询 status，最终返回 `DERIVED_READY` | P0 |
| SDK-E2E-026 | Wait | 上传等待 DERIVED_VALIDATION_FAILED | 准备会被 worker validation fail 的数据 | 1. 执行 upload `--wait` | SDK 在 `DERIVED_VALIDATION_FAILED` 停止等待并返回该状态 | P0 |
| SDK-E2E-027 | Wait | wait 超时 | 设置极短 `--max-wait 1`，后端未到 terminal | 1. 执行 upload/status wait | SDK 抛超时错误，包含 last status | P1 |
| SDK-E2E-028 | Wait | transient poll error 可恢复 | 模拟 status 前一次 502，后一次成功 | 1. 执行 wait | 未超过 `max_poll_errors` 时继续轮询，最终返回成功状态 | P1 |
| SDK-E2E-029 | Wait | 连续 poll error 超限 | 模拟 status 连续失败 | 1. 执行 wait，设置 `--max-poll-errors 2` | SDK 抛 `Failed to poll upload ... after 2 consecutive errors` | P1 |
| SDK-E2E-030 | Status | 查询 upload 状态 | 已有 upload ID | 1. 执行 `prismax status <upload_id>` | 输出 Upload ID、Status、Episodes、Serial number、Created at 等摘要 | P0 |
| SDK-E2E-031 | Status | JSON 格式查询 | 已有 upload ID | 1. 执行 `prismax status <upload_id> --json` | 输出完整 JSON，可用于 QA 断言 | P1 |
| SDK-E2E-032 | Resume | raw upload 中断后 resume | upload session 已创建，但部分 raw PUT 失败，upload 仍为 `UPLOADING` | 1. 执行错误提示中的 `prismax resume <upload_id> <original_folder>` | SDK 调用 resume API；只上传后端返回 signed URL 的缺失文件；manifest 上传后流程继续 | P0 |
| SDK-E2E-033 | Resume | resume 使用不完整 folder | 只传缺失文件 folder，不含完整原始 episode | 1. 执行 resume | 本地校验失败或后端无法匹配；提示必须使用原始完整 folder | P0 |
| SDK-E2E-034 | Resume | terminal status 不允许 resume | upload 已是 `DERIVED_READY/FAILED` | 1. 执行 resume | 后端拒绝；SDK 返回 api error；提示应创建新 upload | P1 |
| SDK-E2E-035 | CLI | `--json` 输出 raw response | 正常 upload/status/resume 场景 | 1. 分别执行带 `--json` 的命令 | 输出合法 JSON，便于自动化解析 | P2 |
| SDK-E2E-036 | CLI | 自定义 timeout/retries/concurrency | 网络较慢或 mock signed URL | 1. 执行 upload 带 `--timeout 120 --retries 5 --concurrency 2` | 命令接受参数；上传稳定完成；失败时按 retries 行为报错 | P2 |
| SDK-E2E-037 | Error | API request 网络失败 | 模拟 API timeout | 1. 执行 status/upload | SDK 抛 `PrismaxApiError`，错误信息含 `PrismaX API request failed` | P1 |
| SDK-E2E-038 | Error | signed URL PUT 失败 | 模拟某个 signed URL 返回 500 | 1. 执行 upload | SDK 抛 `PrismaxApiError`；错误包含失败的 relative path；提示 resume 命令 | P0 |
| SDK-E2E-039 | Base URL | 非 localhost 使用 http base_url | 执行时传 `--base-url http://example.com` | 1. 执行 status/upload | 本地校验失败；提示 non-local host 必须使用 `https://` | P1 |
| SDK-E2E-040 | Base URL | localhost 可用 http base_url | 本地有测试 server | 1. 执行 `--base-url http://localhost:<port>` | SDK 接受 localhost http，用于本地 mock 测试 | P2 |

---

## 九、QA 验证建议

建议按以下顺序验证：

1. 先跑本地 unit tests，确认 SDK helper 行为稳定。
2. 使用小文件 mock 数据验证本地扫描与校验失败场景。
3. 使用一个真实 upload API key 验证合法单 episode 上传。
4. 使用 `--wait` 验证 worker 处理完成状态。
5. 制造 signed URL 上传失败或断网场景，验证 resume 提示与恢复。
6. 验证 operator/admin/普通用户 key 权限差异。
7. 最后验证多 episode、additional videos、失败数据和移动/长耗时场景。

历史源码测试目录已经移除，可执行 CLI smoke test 确认安装结果：

```bash
python -m prismax --help
```

---

## 十、验收标准

- SDK 能成功安装，并暴露 `prismax upload/resume/status` CLI。
- 合法数据目录可成功创建 upload session、上传 raw files、上传 manifest。
- 不合法目录在本地被拦截，不应创建 upload session。
- Upload API key 权限正确，Download API key 不能上传。
- `task_id` 与 `scenario` 两种方式均可覆盖，scenario 异常有明确提示。
- `--wait` 能正确处理 success/fail/partial/timeout/poll error。
- raw upload 失败时错误信息包含 upload ID、失败文件和 resume 命令。
- resume 必须使用原始完整 folder，并能恢复 `UPLOADING` 状态的 upload。
- CLI `--json` 输出可被自动化测试解析。
- 文档中所有命令和 Python API 示例均可被 QA 直接复用。
