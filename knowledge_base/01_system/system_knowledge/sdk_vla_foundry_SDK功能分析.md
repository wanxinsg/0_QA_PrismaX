# sdk-vla-foundry SDK 功能分析

## 1. SDK 定位

`sdk-vla-foundry` 是 PrismaX 面向机器人数据上传场景的 Python SDK，发布包名为 `prismax`。它的核心目标是把本地采集好的 episode 数据上传到 PrismaX 数据平台，并在上传前完成必要的本地结构校验。

该 SDK 当前能力集中在“上传链路”，不是完整的数据处理或 QA Worker：

- 扫描本地数据目录，识别 `.mcap` 与 `.mp4` 文件。
- 校验每个 episode 是否满足 PrismaX 上传结构要求。
- 根据 task ID 或 scenario/task name 解析 PrismaX 任务。
- 调用 PrismaX Data API 创建上传会话或恢复上传会话。
- 使用服务端返回的 signed URL 并发上传原始文件。
- 为每个 episode 生成 `_MANIFEST.json` 并上传。
- 查询上传状态，并可等待后端 Worker 处理完成。
- 提供 Python API 与 `prismax` 命令行工具。

项目入口与主要模块：

```text
sdk-vla-foundry/
  README.md
  pyproject.toml
  prismax/
    __init__.py
    cli.py
    client.py
    upload.py
    scanner.py
    manifest.py
    scenarios.py
    errors.py
  tests/
    test_upload_helpers.py
```

## 2. 安装与运行环境

`pyproject.toml` 中定义：

- 包名：`prismax`
- 当前版本：`0.1.4`
- Python 版本要求：`>=3.9`
- 主要依赖：`requests>=2.31.0`
- 命令行入口：`prismax = prismax.cli:main`
- License：`PolyForm Noncommercial License 1.0.0`

默认 API 地址：

```text
https://data.prismaxserver.com
```

环境变量：

- `PRISMAX_API_KEY`：上传 API Key，上传、恢复、状态查询需要。
- `PRISMAX_BASE_URL`：覆盖默认 API 地址，内部测试环境可使用。

安全限制：

- 非本地地址必须使用 `https://`。
- `http://` 只允许 `localhost`、`127.0.0.1`、`::1`。
- API Key 会放在请求头 `X-API-Key` 中。

## 3. 对外 Python API

`prismax/__init__.py` 暴露了主要接口：

```python
import prismax

prismax.upload(...)
prismax.resume(...)
prismax.status(...)
prismax.wait_for_upload(...)
prismax.list_scenarios(...)

prismax.scan_folder(...)
prismax.validate_mcap_mp4(...)
prismax.select_primary_video_paths(...)
prismax.episode_keys(...)
```

主要异常类型：

```python
prismax.PrismaxError
prismax.PrismaxAuthError
prismax.PrismaxValidationError
prismax.PrismaxApiError
```

含义：

- `PrismaxValidationError`：本地输入非法，例如目录结构不符合要求、缺少 serial number、task_id 不是整数。
- `PrismaxAuthError`：API Key 缺失、无权限或服务端返回 401/403。
- `PrismaxApiError`：PrismaX API 请求失败、signed URL 上传失败、轮询超时等。

## 4. CLI 功能

SDK 提供 `prismax` 命令行工具。

### 4.1 列出可用 scenario

```bash
prismax scenarios
```

该命令调用 `/data/tasks`，默认不强制要求 API Key。输出默认是一行一个 scenario，也支持 `--json` 输出原始 JSON。

### 4.2 上传数据

```bash
prismax upload ./data \
  --scenario "Pick and place packaged food items" \
  --serial-number robot_serial_number
```

也可以直接传 task ID：

```bash
prismax upload ./data \
  --task-id 123 \
  --serial-number robot_serial_number
```

常用参数：

- `--api-key`：显式传入 API Key。
- `--base-url`：显式覆盖 API 地址。
- `--wait`：上传后等待 Worker 处理到终态。
- `--max-wait`：最大等待秒数，默认 1800。
- `--poll-interval`：轮询间隔秒数，默认 10。
- `--timeout`：HTTP 超时时间，默认 60。
- `--retries`：上传重试次数，默认 3。
- `--concurrency`：并发上传文件数，默认 5。
- `--json`：打印完整 API 返回。

默认 CLI 摘要只打印：

- Upload ID
- Status
- Episodes
- Serial number
- Created at

不会打印 signed URL、bucket、expires_at 等原始字段。需要完整信息时使用 `--json`。

### 4.3 查询状态

```bash
prismax status 123
```

状态查询需要上传 API Key 或有权限访问该 upload 的 key。

### 4.4 恢复上传

```bash
prismax resume 123 ./data
```

恢复上传的要求：

- 必须传入原始完整上传目录，而不是只传失败文件目录。
- SDK 会把完整文件列表发给 API，由 API 判断哪些文件仍需要 signed URL。
- 只适用于仍处于 `UPLOADING` 状态的 upload。
- 一旦后端已经开始处理或进入终态，应创建新上传。

## 5. 上传数据目录规范

SDK 期望每个 episode 由一个根目录 `.mcap` 文件和一个同名 episode 文件夹组成：

```text
data/
  1.mcap
  1/
    high.mp4
    left.mp4
    right.mp4
```

每个 episode 的最低要求：

- 根目录必须有且只有一个 `{episode}.mcap`。
- 必须有 `{episode}/` 文件夹。
- episode 文件夹下至少 3 个 `.mp4` 文件。
- 必须能识别出三类主视频：
  - `left`：文件名包含 `left`
  - `right`：文件名包含 `right`
  - `env/high`：文件名不包含 `left` 或 `right`

额外视频允许存在，例如：

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

这些额外视频会被上传，也会进入 manifest，但只有主视频用于后续预览、QA、去重等派生处理。

## 6. 本地扫描与校验逻辑

扫描逻辑位于 `prismax/scanner.py`。

### 6.1 扫描行为

`scan_folder(folder)` 会：

- 递归扫描目录下所有文件。
- 跳过隐藏文件和隐藏目录，例如 `.DS_Store`、`._left.mp4`、`.hidden.mp4`。
- 跳过已有 `_MANIFEST.json`，因为 SDK 会重新生成 manifest。
- 记录每个文件：
  - `relative_path`
  - 本地绝对路径
  - `size_bytes`
  - `content_type`

### 6.2 路径规则

允许的结构只有两层：

```text
根目录：
  {episode}.mcap

episode 文件夹：
  {episode}/{video}.mp4
```

拒绝的情况包括：

- 根目录下出现非 `.mcap` 文件。
- episode 文件夹中出现非 `.mp4` 文件。
- 出现嵌套子目录，例如 `1/nested/left.mp4`。
- episode 文件夹名以 `.mcap` 结尾。
- `.MP4` 等大写扩展名。SDK 只接受小写 `.mp4`。

### 6.3 主视频选择规则

主视频选择函数为 `select_primary_video_paths(video_paths)`。

分类规则：

- 文件名包含 `left`：左视角。
- 文件名包含 `right`：右视角。
- 其他 `.mp4`：环境视角或 high 视角。

优先级规则：

- env/high 优先精确文件名 `high.mp4` 或 `env.mp4`。
- left 优先 `left.mp4`。
- right 优先 `right.mp4`。
- 如果没有精确名称，则按文件名排序选择第一个。

因此在以下目录中：

```text
1/high.mp4
1/high2.mp4
1/left.mp4
1/left2.mp4
1/right.mp4
1/right2.mp4
```

主视频为：

```text
env/high: 1/high.mp4
left:     1/left.mp4
right:    1/right.mp4
```

## 7. Manifest 生成逻辑

Manifest 逻辑位于 `prismax/manifest.py`。

SDK 上传前会在文件列表中增加每个 episode 的 manifest 占位：

```json
{
  "relative_path": "1/_MANIFEST.json",
  "size_bytes": null,
  "content_type": "application/json"
}
```

实际上传文件完成后，SDK 会为每个 episode 生成 manifest payload，并通过 signed URL 上传。

Manifest 内容结构：

```json
{
  "manifest_version": 1,
  "upload_id": 123,
  "episode_key": "1",
  "machine_id": "machine-1",
  "task_id": 9,
  "created_at_utc": "2026-07-15T00:00:00+00:00",
  "files": [
    {
      "relative_path": "1.mcap",
      "size_bytes": 123,
      "content_type": "application/octet-stream"
    },
    {
      "relative_path": "1/high.mp4",
      "size_bytes": 456,
      "content_type": "video/mp4"
    }
  ]
}
```

Manifest 只收录该 episode 相关文件：

- `{episode}.mcap`
- `{episode}/...`

## 8. 上传主流程

上传入口为 `prismax.upload.upload()`。

完整流程：

1. 校验 `serial_number` 必填。
2. 创建 `PrismaXClient`，读取 API Key、base URL、timeout、concurrency、retries。
3. 调用 `scan_folder()` 扫描本地目录。
4. 调用 `validate_mcap_mp4()` 校验 episode 结构。
5. 解析 task：
   - 如果传入 `task_id`，直接转为整数。
   - 如果传入 `scenario` 或 `task_name`，调用 `/data/tasks` 进行大小写不敏感匹配。
6. 根据文件列表和 episode keys 构造 API files payload，并追加 manifest 占位。
7. 调用 `POST /v1/data/upload-sessions` 创建上传会话。
8. 从返回结果中读取 signed URLs。
9. 并发上传本地原始文件。
10. 为每个 episode 生成并上传 `_MANIFEST.json`。
11. 如果指定 `wait=True`，继续轮询 upload 状态直到终态。
12. 返回去掉 `signed_urls` 后的公开结果。

创建上传会话请求体核心字段：

```json
{
  "task_id": 12,
  "serial_number": "MD100101000019205Z00082",
  "files": [
    {
      "relative_path": "1.mcap",
      "size_bytes": 123,
      "content_type": "application/octet-stream"
    },
    {
      "relative_path": "1/high.mp4",
      "size_bytes": 456,
      "content_type": "video/mp4"
    },
    {
      "relative_path": "1/_MANIFEST.json",
      "size_bytes": null,
      "content_type": "application/json"
    }
  ]
}
```

注意：创建上传会话使用的是 `serial_number`，不是客户端传入 `machine_id`。服务端会根据 serial number 解析并返回 `machine_id`，后续 manifest 使用这个 resolved machine ID。

## 9. 恢复上传流程

恢复入口为 `prismax.upload.resume()`。

流程与普通上传类似，但创建会话改为：

```text
POST /v1/data/upload-sessions/{upload_id}/resume
```

请求体包含完整 files payload：

```json
{
  "files": [...]
}
```

API 返回本次仍需上传的 signed URLs。SDK 只上传有 signed URL 的文件和 manifest。

如果恢复过程中失败，错误信息会提示再次执行：

```bash
prismax resume <upload_id> <folder>
```

## 10. 状态查询与等待逻辑

状态查询：

```text
GET /v1/data/uploads/{upload_id}
```

等待函数为 `wait_for_upload()`。

终态集合：

```text
DERIVED_READY
DERIVED_VALIDATION_FAILED
FAILED
DERIVED_PARTIALLY_READY
```

轮询行为：

- 默认每 10 秒查询一次。
- 默认最多等待 1800 秒。
- 短暂 API 错误可容忍，默认连续 3 次轮询错误后抛出 `PrismaxApiError`。
- 超过最大等待时间会抛出超时错误，并包含最后一次状态。

## 11. API Client 行为

`PrismaXClient` 位于 `prismax/client.py`。

主要方法：

| 方法 | API/行为 | 用途 |
| --- | --- | --- |
| `create_upload_session()` | `POST /v1/data/upload-sessions` | 创建上传会话 |
| `resume_upload_session()` | `POST /v1/data/upload-sessions/{upload_id}/resume` | 恢复上传 |
| `list_tasks()` | `GET /data/tasks` | 获取任务列表、scenario 列表 |
| `get_upload()` | `GET /v1/data/uploads/{upload_id}` | 查询上传状态 |
| `upload_file_to_signed_url()` | `PUT signed_url` | 上传原始文件 |
| `upload_json_to_signed_url()` | `PUT signed_url` | 上传 manifest |
| `upload_files()` | ThreadPoolExecutor | 并发上传多个文件 |

请求头：

```text
Content-Type: application/json
User-Agent: prismax-sdk/<version>
X-API-Key: <api_key>
```

signed URL 上传不带 `X-API-Key`，只带对应文件的 `Content-Type`。

重试策略：

- API 普通请求没有显式重试。
- signed URL PUT 上传有重试，默认 3 次。
- 失败后指数退避，单次等待上限 10 秒。

## 12. 任务解析逻辑

`resolve_task_id()` 支持两种方式：

### 12.1 直接传 task_id

```python
prismax.upload("./data", task_id=12, serial_number="...")
```

SDK 会尝试转成整数。如果失败，抛出 `PrismaxValidationError`。

### 12.2 通过 scenario/task_name 匹配

```python
prismax.upload(
    "./data",
    scenario="Pick and place packaged food items",
    serial_number="..."
)
```

匹配规则：

- 调用 `list_tasks()` 获取任务列表。
- 在任务的 `scenario`、`task_name`、`name`、`title` 字段中匹配。
- 匹配时会去除首尾空白、合并连续空白、转换为小写。
- 如果没有匹配，会在错误信息中展示前 10 个可用任务名。
- 如果匹配多个任务，会要求用户改用 `task_id`。

## 13. list_scenarios 行为

`list_scenarios()` 调用 `/data/tasks`，提取 task 中的 `scenario` 字段。

规则：

- 跳过空 scenario。
- 去重。
- 保持 API 返回顺序。
- 不强制要求 API Key。

## 14. SDK 与后端/Worker 的边界

SDK 负责：

- 本地文件结构校验。
- 文件列表元数据生成。
- 创建/恢复上传会话。
- 上传原始文件和 manifest。
- 查询 upload 状态。

SDK 不负责：

- 解析 MCAP 内容。
- 校验视频时长一致性。
- 生成视频预览。
- 派生数据处理。
- QA 规则判定。
- 重复数据检测。
- 后端 Worker 任务调度。

README 中说明，额外视频会被上传和纳入下载 manifest，并会在后端检查时长一致性；主三路视频用于派生预览、QA 和重复检测。这些属于服务端/Worker 侧能力，不在 SDK 本地实现中。

## 15. 对 QA/测试的重点关注

基于 SDK 当前实现，建议 QA 重点覆盖以下场景。

### 15.1 目录结构校验

- 正常单 episode：`1.mcap + 1/high.mp4 + 1/left.mp4 + 1/right.mp4`。
- 多 episode。
- episode 缺少 `.mcap`。
- episode 缺少 `left/right/env` 任一主视频。
- episode 文件夹中 MP4 数量少于 3。
- 根目录出现非法文件。
- episode 目录出现非 `.mp4` 文件。
- 嵌套目录。
- 大写扩展名 `.MP4`。
- 隐藏文件是否被忽略。
- 已存在 `_MANIFEST.json` 是否被忽略并重新生成。

### 15.2 主视频选择

- `high.mp4/left.mp4/right.mp4` 应优先于 `high2.mp4/left2.mp4/right2.mp4`。
- 没有精确名称时，按文件名排序选择主视频。
- 文件名包含 `left` 或 `right` 的额外视频不会误选为 env。

### 15.3 上传会话

- `serial_number` 必填。
- 创建会话请求体包含 `task_id`、`serial_number`、files。
- files 中包含所有原始文件和每个 episode 的 `_MANIFEST.json` 占位。
- SDK 返回结果应隐藏 `signed_urls`。
- signed URL 缺失时，SDK 会跳过对应文件上传。

### 15.4 恢复上传

- resume 使用完整原始目录。
- resume 请求体包含完整 files payload。
- 只上传服务端返回 signed URL 的文件。
- 失败信息中包含可执行的 `prismax resume <upload_id> <folder>` 提示。

### 15.5 等待与状态

- `DERIVED_READY` 成功终态。
- `DERIVED_PARTIALLY_READY` 也是终态。
- `DERIVED_VALIDATION_FAILED` 与 `FAILED` 是失败类终态，但函数会返回当前状态，由调用方解释。
- 连续轮询错误达到上限后抛错。
- 超时后错误信息包含 upload ID、等待秒数、最后状态。

### 15.6 认证与 API 错误

- 缺少 API Key 应抛 `PrismaxAuthError`。
- 401/403 应抛 `PrismaxAuthError`。
- API 返回 `success: false` 应抛 `PrismaxApiError` 或 `PrismaxAuthError`。
- 非 JSON 响应会被包装为错误信息。
- signed URL PUT 失败应包含相对路径，方便定位文件。

## 16. 典型使用示例

### 16.1 Python 上传

```python
import prismax

result = prismax.upload(
    "./data",
    scenario="Pick and place packaged food items",
    serial_number="MD100101000019205Z00082",
)

print(result["upload_id"])
```

### 16.2 Python 上传并等待

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=123,
    serial_number="MD100101000019205Z00082",
    wait=True,
    max_wait=3600,
    poll_interval=5,
)

print(result["status"])
```

### 16.3 Python 错误处理

```python
import prismax

try:
    prismax.upload(
        "./data",
        scenario="Pick and place packaged food items",
        serial_number="MD100101000019205Z00082",
    )
except prismax.PrismaxValidationError as exc:
    print(f"Invalid upload folder: {exc}")
except prismax.PrismaxAuthError as exc:
    print(f"API key or permission error: {exc}")
except prismax.PrismaxApiError as exc:
    print(f"PrismaX API error: {exc}")
```

### 16.4 CLI 上传并等待

```bash
export PRISMAX_API_KEY="pxu_your_upload_api_key"

prismax upload ./data \
  --scenario "Pick and place packaged food items" \
  --serial-number MD100101000019205Z00082 \
  --wait \
  --max-wait 3600
```

## 17. 总结

`sdk-vla-foundry` 是 PrismaX 数据上传链路的轻量 SDK。它的价值在于把“本地 episode 文件结构校验、任务解析、上传会话创建、signed URL 文件上传、manifest 生成、上传状态查询”封装成稳定的 Python API 和 CLI。

从系统视角看，它位于“本地采集数据”和“PrismaX Data API/后端 Worker”之间。SDK 保证上传输入结构可控、文件元数据完整、上传失败可恢复；更深层的 MCAP 解析、视频一致性检查、预览生成、QA 和去重逻辑则由 PrismaX 后端处理。
