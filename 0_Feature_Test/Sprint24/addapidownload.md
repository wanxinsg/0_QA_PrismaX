# SDK API Package Download 改动逻辑与 E2E 测试

> 分析日期：2026-08-20
> 仓库：`QA_RobotDataXTest/UPLOAD_DATA_APIKEY/sdk-vla-foundry`（分支 `testing`）
> Commit：`5e3ae4ef17cf73e834ce2867d9d3e6611b51db18` — `Add API package downloads`
> 版本：`0.2.1` → `0.3.0b1`
> 数据来源：SDK 源码、单元测试、README，及后端 `POST /v1/data/download-sessions` 实现对照；未执行远端拉取，未跑真实下载。

---

## README 参考：5. 下载 API Package

> 翻译自 `sdk-vla-foundry` README 第 5 节 *Download An API Package*，供测试对照。原文位置：`QA_RobotDataXTest/sdk-vla-foundry/README.md`。

创建一个前缀为 `pxa_` 的 Download API Key，并从 PrismaX App 中复制 Package ID。前缀为 `pxu_` 的 Upload Key **不能**用于下载数据。

```bash
export PRISMAX_DOWNLOAD_API_KEY="pxa_your_download_api_key"
```

使用 Python 下载 Package：

```python
import prismax

result = prismax.download(
    "pkg_your_package_id",
    output="./dataset",
)
print(result["file_count"])
```

或使用 CLI：

```bash
prismax download pkg_your_package_id --output ./dataset
```

SDK 会下载该 Package 返回的 MCAP、主视频，以及所有 additional videos。下载时会自动带上每个文件对应的 CDN Cookie。

## README 参考：CLI Reference

> 翻译自 `sdk-vla-foundry` README *CLI Reference*，供测试对照。

列出可用 scenario：

```bash
prismax scenarios
```

按期望文件夹结构上传：

```bash
prismax upload ./data \
  --scenario "Pick and place packaged food items" \
  --serial-number robot_serial_number
```

创建并上传 JSON 定义的 upload：

```bash
prismax upload-data ./prismax_upload.json
```

恢复上述两种上传：

```bash
prismax resume 123 ./data
prismax resume-data 123 ./prismax_upload.json
```

查看状态：

```bash
prismax uploads
prismax uploads --limit 20
prismax status 123
prismax status 123 --json
```

下载已有的 API Package：

```bash
prismax download pkg_your_package_id --output ./dataset
```

使用 `--wait` 等待 worker 处理完成。默认最长等待 30 分钟：

```bash
prismax upload-data ./prismax_upload.json --wait
prismax upload-data ./prismax_upload.json --wait --max-wait 3600
```

常用上传参数：

```bash
prismax upload-data ./prismax_upload.json --concurrency 8 --timeout 120 --retries 5
prismax upload-data ./prismax_upload.json --no-progress
```

创建或恢复 upload 时，默认最多等待 5 分钟；普通 API 请求和单个文件上传使用 `--timeout`。通常这两类超时都不需要改。

---

## 1. 分析范围

分析本次 commit 引入的 **SDK 下载功能**，以及为支持下载所做的鉴权和环境变量改动。既有上传功能仅在被本次改动直接触及时纳入回归。

| 文件 | 改动内容 |
| --- | --- |
| `prismax/download.py` | 新增 — Python 下载入口 |
| `prismax/client.py` | 双 Key 环境变量、前缀校验、`create_download_session`、CDN 并发下载 |
| `prismax/cli.py` | 新增 `prismax download` 子命令 |
| `prismax/upload.py` | 所有上传函数改用 `_build_client()`，强制 `pxu_` 前缀 |
| `prismax/__init__.py` | 导出 `download` / `create_download_session`，版本号升至 `0.3.0b1` |
| `pyproject.toml` | 版本和描述更新 |
| `README.md` | 新增第 5 节 Download An API Package |
| `tests/test_download.py` | 新增 7 个单元测试 |

后端对照接口（SDK 调用，不属于本次 commit）：`POST /v1/data/download-sessions`，Header `X-API-Key: pxa_...`，Body `{"package_id": "pkg_..."}`。

---

## 2. 总体结论

本次改动将 SDK 从「只上传」扩展为「上传 + 下载 API Package」。用户持 `pxa_` Download Key 和 Package ID，可一次性将 Package 内所有 Episode 的 MCAP、三路主视频及 additional videos 下载到本地。

**核心调用链：**

```text
pxa_ key + package_id
  → POST /v1/data/download-sessions
  → 解析 samples[].assets.{mcap,env,left,right} + additional_videos
  → 校验 relative_path 安全性
  → 带各 asset 的 CDN Cookie 并发 GET
  → 写入 output/<relative_path>
```

**主要风险：**

1. **破坏性变更**：旧环境变量 `PRISMAX_API_KEY` 不再生效；上传须改用 `PRISMAX_UPLOAD_API_KEY`。
2. **Key 类型隔离**：`pxu_` 无法下载，`pxa_` 无法上传；混用会被 SDK 本地立即拒绝。
3. **Cookie 绑定在每个 asset**：SDK 不支持 sample 级 fallback，完全依赖后端为每个 asset 返回 `auth.cookie_header`。
4. **不校验 MD5、不跳过已有文件**：传输失败后可能留下半文件。
5. **Session 创建成功即可能写入下载历史/计数**：文件未下完不等于后端未记账。

---

## 3. 改动逻辑

### 3.1 鉴权：单 Key → 双 Key

| 操作 | 环境变量 | Key 前缀 | 典型入口 |
| --- | --- | --- | --- |
| 上传 / status / resume / wait | `PRISMAX_UPLOAD_API_KEY` | `pxu_` | `prismax.upload()`、`status()`、CLI `upload` |
| 下载 | `PRISMAX_DOWNLOAD_API_KEY` | `pxa_` | `prismax.download()`、CLI `download` |
| 列 scenario | 无需 Key | — | `prismax.list_scenarios()` |

`PrismaXClient` 新增两个参数：
- `api_key_env`：指定从哪个环境变量读取 Key。
- `api_key_prefix`：本地前缀校验，不匹配立即抛 `PrismaxAuthError`，不会发起 HTTP 请求。

**回归影响**：`upload.py` 内所有函数（`upload` / `resume` / `status` / `recent_uploads` / `wait_for_upload`）全部改用 `_build_client()`，并强制 `pxu_` 前缀。原来只设 `PRISMAX_API_KEY` 的脚本在本版本会直接报 `PrismaxAuthError`。

### 3.2 创建 Download Session

1. `package_id` 去除首尾空格；空值直接抛 `PrismaxValidationError("package_id is required.")`，不发 HTTP。
2. 用 Download Client 调 `POST /v1/data/download-sessions`，超时用 `session_timeout`（默认 300 秒）。
3. 请求体仅 `{"package_id": ...}`，**不携带 Idempotency-Key**。
4. 成功后返回后端 `data` 整包，`download()` 继续拉取文件。

**后端行为：**
- 校验 Key ACTIVE、用户有有效 Data Membership、Package 属于该 Key 用户、Package 状态为 `ACTIVE`、Package 内有 Episode。
- 写入 `data_downloads`（mode=`api`），为每个 asset 生成 Cloud CDN signed cookie；cookie 写在 `asset.auth.cookie_header`，**非** sample 级。
- Session 创建成功后即写入下载历史、将 Episode 加入 My Data、标记 download 为 READY 并增加 `download_count`。
- 额度不足返回 402，无会员/无权限返回 403。SDK 将 401/403 映射为 `PrismaxAuthError`，其余（含 402）映射为 `PrismaxApiError`，402 不额外暴露 `data.quota`。

### 3.3 解析 Session 并落盘

`_download_items()` 按每个 sample 的固定顺序收集 asset：`mcap → env → left → right → additional_videos[]`。

每个 asset 必须同时包含 `relative_path`、`url`、`auth.cookie_header`，缺任一字段抛 `PrismaxApiError`；asset 列表为空也报错。

路径安全 `_safe_destination()`：将 `\` 规范化为 `/`，拒绝空路径、绝对路径、含 `..` 的路径，按 posix 分段拼接至 `output`。重复目标路径抛 `PrismaxValidationError`，父目录自动创建。

**本地目录结构**（以 `episode_1` 为例）：

```text
output/
  episode_1.mcap
  episode_1/high.mp4
  episode_1/left.mp4
  episode_1/right.mp4
  episode_1/<additional>.mp4
```

多 Episode Package 在 `output` 根下并列存放，**不加** `upload_<id>/` 前缀。这与旧手工脚本 `qa_download.py`（按 upload_id 分子目录）和 Manifest 脚本的目录结构不同。

### 3.4 CDN 文件下载

`download_file_from_cdn()`：

- `GET url`，Header 仅 `Cookie: <cookie_header>`，`stream=True`，1 MB chunk 写入本地。
- 失败后 exponential backoff 重试（`min(2^attempt, 10)` 秒），最多 `retries` 次（默认 3，传 0 按 1 次处理）。
- 重试以 `wb` 重新打开目标文件，旧内容被截断；**耗尽重试后半文件留在磁盘**。
- **不校验** `md5_hash` 和 `size_bytes`，**不跳过**已有文件，每次全量覆盖。

`download_files()` 使用 `ThreadPoolExecutor`（默认 `concurrency=5`）并发下载。任一文件失败即抛错，其余已提交的任务仍在运行，目录可能处于部分完整状态。

进度输出到 stderr：`Download {i}/{n}: {relative_path}`，可通过 `--no-progress` 关闭。

### 3.5 Python / CLI 接口

```python
import prismax

result = prismax.download("pkg_xxx", output="./dataset")
# 返回: download_id, package_id, episode_count, file_count, output
```

```bash
export PRISMAX_DOWNLOAD_API_KEY="pxa_..."
prismax download pkg_xxx --output ./dataset
```

CLI 支持参数：`package_id`、`--output`（默认 `./dataset`）、`--api-key`、`--base-url`、`--timeout`、`--session-timeout`、`--retries`、`--concurrency`、`--no-progress`。

成功后 stdout 打印：`Download ID` / `Package ID` / `Episodes` / `Files` / `Output`。其中 `episode_count = len(session.samples)`，`file_count` 为实际 asset 数量。

### 3.6 与官方示例脚本的差异

前端 `apiPackageExample.js` 和旧 QA 脚本具备以下 SDK 中缺失的能力：

| 能力 | 官方示例 | SDK |
| --- | --- | --- |
| Cookie fallback（asset → sample 级） | ✅ | ❌ |
| MD5 校验 | ✅ | ❌ |
| 失败时删除半文件后重试 | ✅ | ❌ |

后端当前将 Cookie 写在 asset 级，Happy Path 可正常工作；MD5 校验和半文件清理是已知质量缺口。

### 3.7 现有单元测试覆盖范围

`tests/test_download.py` 已覆盖：下载使用 `PRISMAX_DOWNLOAD_API_KEY`、upload 操作使用 `PRISMAX_UPLOAD_API_KEY`、Key 类型互拒（`pxu_` 不能下载，`pxa_` 不能上传）、解析 additional videos 并按 asset 带各自 cookie、CDN 下载发送 Cookie 并写文件、CLI 打印 Download ID / Files。

**未覆盖**：空 `package_id`、路径穿越、重复路径、缺 cookie/url、空 samples、重试逻辑、半文件行为、真实 402/403、MD5 校验、多 episode 目录结构。

---

## 4. 测试分析

### 4.1 测试层级

| 层级 | 目标 |
| --- | --- |
| SDK 单测 | Key 前缀、环境变量读取、路径安全、解析顺序、CLI 参数 |
| API 合同 | Session 状态码、鉴权、Package 所有权、配额、Package 状态流转 |
| E2E | 真实 `pxa_` + 真实 Package + CDN 落盘 |
| 上传回归 | 上传仍只用 `pxu_`；旧 `PRISMAX_API_KEY` 按发布说明预期报错 |
| 非功能 | 并发一致性、大文件超时、Cookie TTL、中断后残留 |

### 4.2 测试账号与数据准备

- **包所有者账号**：有有效 Data Membership，持有 ACTIVE `pxa_` Download Key 及 ACTIVE `pxu_` Upload Key。
  - 测试 Package A：ACTIVE，1 个 Episode，含 mcap + env/left/right + 至少 1 个 additional video。
  - 测试 Package B：ACTIVE，2 个及以上 Episode。
- **非包所有者账号**：另一名合法用户，持有自己的 ACTIVE `pxa_` Key 及只属于该账号的 Package。
- **会员失效账号**：Membership 已过期，但 `pxa_` Key 仍为 ACTIVE。
- **额度将满账号**（剩余 1 个 Episode 额度）、**额度已满账号**（剩余 0）。
- 辅助数据：INACTIVE Package、无 Episode 的空 Package、干净输出目录、已有同名文件的输出目录。

### 4.3 主要风险

| ID | 级别 | 风险描述 | 验证方式 |
| --- | --- | --- | --- |
| R01 | P0 | `PRISMAX_API_KEY` 不再生效，旧上传脚本直接 AuthError | 发布说明须覆盖；用旧 env 变量跑上传确认报错 |
| R02 | P0 | `pxu_` / `pxa_` 互用被本地拒绝 | SDK 层直接验证；后端侧也确认不串权限 |
| R03 | P0 | Cookie 仅读 `asset.auth.cookie_header`，无 sample 级 fallback | 用真实 Session 确认每个 asset 均含 cookie |
| R04 | P0 | Session 创建成功即记账，CDN 传输失败不回滚历史/计数 | 模拟单文件失败，查 `data_downloads` 和 `download_count` |
| R05 | P1 | 不校验 MD5，文件损坏 SDK 仍视为成功 | 手动对比本地文件 MD5 与 Session 返回值 |
| R06 | P1 | 传输失败后半文件留盘，重跑覆盖但不清理无关残留 | 中断后检查目录；重跑后验证文件完整性 |
| R07 | P1 | 多 Episode 平铺在 output 根下，与旧脚本目录结构不同 | 对照 README 验收实际目录树 |
| R08 | P1 | 不传 Idempotency-Key，重复调用多次创建 Session | 连续两次 download 同一 Package，确认 history 条数 |
| R09 | P1 | 402 映射为普通 ApiError，CLI 无法展示 quota 明细 | 超额时确认 stderr 是否足够可诊断 |
| R10 | P2 | `retries=0` 实际执行 1 次 | 确认文档与行为一致 |
| R11 | P2 | 默认 `base_url` 指向 beta pipeline | prod 需显式设置 `PRISMAX_BASE_URL` |

### 4.4 发布前确认项

1. 发版说明是否已说明 `PRISMAX_API_KEY` 不再生效（breaking change）。
2. 下载目录结构以 `relative_path` 为准、不加 `upload_id/` 前缀，是否符合产品预期。
3. 重复 download 同一 Package 是否允许多次创建 Session（R08）。
4. 是否要求 SDK 校验 `md5_hash`（R05）。
5. Cookie TTL 内大 Package 是否能下完；默认单文件 timeout 60s 是否够用。

---

## 5. E2E 测试用例

进度：`notstart` | `inprogress` | `pendingfix` | `done`

| 模块 | 用例范围 | 数量 | 进度 | 备注 |
| --- | --- | --- | --- | --- |
| 5.1 鉴权与环境变量 | SDK-DL-001 ~ 008 | 8 | notstart | |
| 5.2 Python / CLI Happy Path | SDK-DL-009 ~ 016 | 8 | notstart | |
| 5.3 文件内容与目录 | SDK-DL-017 ~ 022 | 6 | notstart | |
| 5.4 后端错误与权限 | SDK-DL-023 ~ 031 | 9 | notstart | |
| 5.5 失败恢复与非功能 | SDK-DL-032 ~ 038 | 7 | notstart | |
| 5.6 上传回归 | SDK-DL-039 ~ 042 | 4 | notstart | 本 commit 改动了上传 client 构造 |

### 5.1 鉴权与环境变量

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SDK-DL-001 | P0 | 下载读取 `PRISMAX_DOWNLOAD_API_KEY` | 包所有者账号持有有效 `pxa_` Key；Package 为 ACTIVE | 设置环境变量 `PRISMAX_DOWNLOAD_API_KEY=pxa_...`；调用 `prismax.download(pkg, out)` 时不在代码中传入 `api_key` 参数，让 SDK 自动从环境变量读取 | Session 创建成功，开始拉取文件；请求头 `X-API-Key` 值为 `pxa_` |
| SDK-DL-002 | P0 | 两种 Key 同时存在时下载不误用上传 Key | 同时设置 `PRISMAX_UPLOAD_API_KEY=pxu_...` 和 `PRISMAX_DOWNLOAD_API_KEY=pxa_...` | 调用 `download()` | 请求头使用 `pxa_`；`pxu_` 不出现在 download-sessions 请求中 |
| SDK-DL-003 | P0 | 旧 `PRISMAX_API_KEY` 不能用于下载 | 只设 `PRISMAX_API_KEY=pxa_...`，不设 `PRISMAX_DOWNLOAD_API_KEY` | 调用 `download()` 且不传 `api_key` | 抛 `PrismaxAuthError`，提示设置 `PRISMAX_DOWNLOAD_API_KEY` |
| SDK-DL-004 | P0 | 用 `pxu_` Key 下载被本地拒绝 | 有效 `pxu_` Key | `download(..., api_key="pxu_...")` | 立即抛 `PrismaxAuthError`，错误信息含 `pxa_`；后端无 Session 记录 |
| SDK-DL-005 | P0 | 用 `pxa_` Key 查 upload status 被本地拒绝 | 有效 `pxa_` Key | `prismax.status(upload_id, api_key="pxa_...")` | 抛 `PrismaxAuthError`，错误信息含 `pxu_` |
| SDK-DL-006 | P0 | 不设任何 Key | 清空所有相关环境变量 | `download(pkg, out)` | 抛 `PrismaxAuthError`：`api_key is required or PRISMAX_DOWNLOAD_API_KEY must be set.` |
| SDK-DL-007 | P0 | CLI `--api-key` 覆盖无效的环境变量 | 环境变量为错误/过期 Key；`--api-key` 传入正确 `pxa_` | `prismax download pkg --api-key pxa_valid --output ./out` | 使用 CLI 参数中的 Key，下载成功 |
| SDK-DL-008 | P1 | 空或纯空白的 package_id | 有效 `pxa_` Key | `download("", out)` 和 `download("   ", out)` | 抛 `PrismaxValidationError: package_id is required.`；不发出 HTTP 请求 |

### 5.2 Python / CLI Happy Path

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SDK-DL-009 | P0 | Python 下载单 Episode Package | 包所有者账号；Package A（1 个 Episode，含 mcap + 3 主视频 + 1 个 additional） | `result = prismax.download(pkg, "./dataset")` | 返回 `download_id`、`package_id`、`episode_count=1`、`file_count=5`（或实际值）、`output` 为展开后的绝对路径 |
| SDK-DL-010 | P0 | CLI 下载 | 包所有者账号；Package A（1 个 Episode，含 mcap + 3 主视频 + 1 个 additional） | `prismax download pkg --output ./dataset` | 退出码 0；stdout 打印 Download ID / Package ID / Episodes / Files / Output；stderr 输出逐文件进度 |
| SDK-DL-011 | P1 | CLI `--no-progress` 关闭进度输出 | 包所有者账号；Package A（1 个 Episode，含 mcap + 3 主视频 + 1 个 additional） | `prismax download pkg --output ./dataset --no-progress` | stderr 无逐文件进度；stdout summary 正常打印 |
| SDK-DL-012 | P0 | `create_download_session` 只建 Session 不落盘 | 包所有者账号；有效 Package | 只调用 `prismax.create_download_session(pkg)` | 返回含 samples / assets / url / cookie 的 Session；本地无新增文件 |
| SDK-DL-013 | P0 | 多 Episode Package 全量下载 | Package B（2+ 个 Episode） | Python / CLI 下载 | `episode_count` 等于 sample 数量；每个 Episode 的 mcap 和全部视频均落盘 |
| SDK-DL-014 | P1 | `--output` 默认值为 `./dataset` | 当前工作目录可写 | CLI 不传 `--output` | 文件写入当前目录下的 `dataset` 文件夹 |
| SDK-DL-015 | P1 | `~` 路径自动展开 | 当前系统用户的主目录（即 `~` 对应的路径，如 `/Users/wanxin`）有写权限 | `download(pkg, "~/prismax-dl-test")` | 文件写入 `~` 展开后的实际路径（如 `/Users/wanxin/prismax-dl-test`），不将 `~` 作为字面目录名处理 |
| SDK-DL-016 | P1 | 自定义 `base_url` 生效 | 当前测试环境的 pipeline 地址 | 传入 `base_url` 或设置 `PRISMAX_BASE_URL` | 请求打到指定地址，不走默认 beta URL |

### 5.3 文件内容与目录

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SDK-DL-017 | P0 | 目录结构与 `relative_path` 一致 | Package A，episode_key 如 `episode_1` | 下载后查看目录 | 存在 `episode_1.mcap`、`episode_1/high.mp4`、`episode_1/left.mp4`、`episode_1/right.mp4`、`episode_1/<additional>.mp4`；根目录下无 `upload_<id>/` 前缀 |
| SDK-DL-018 | P0 | additional videos 完整包含且不覆盖主视角 | Package 含 additional video | 对比 Session 中的文件列表与本地文件 | 本地文件与 Session 一一对应；additional 未替代 env/left/right 的位置 |
| SDK-DL-019 | P0 | CDN Cookie 有效且为每文件独立 | 真实 CDN 环境 | ① SDK 正常下载；② 去掉 Cookie 直接 GET 同一 URL | SDK 下载成功（200）；去掉 Cookie 的请求被 CDN 拒绝（403 / 401） |
| SDK-DL-020 | P0 | 文件完整可读 | Session 包含 `size_bytes` | 比对本地文件大小与 Session 返回值 | 大小一致（或与 CDN `Content-Length` 一致）；mcap / mp4 文件可正常打开 |
| SDK-DL-021 | P1 | 同路径文件被覆盖 | output 下已存在同路径但内容不同的文件 | 再次调用 `download()` | 旧文件被新内容覆盖；不跳过 |
| SDK-DL-022 | P1 | MD5 人工抽查（SDK 不做，测试补充） | Session 返回 `md5_hash` | 对本地文件计算 base64 MD5 并比对 | 与 Session 中的值一致；不一致记为缺陷（对应 R05），即使 SDK 返回成功 |

### 5.4 后端错误与权限

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SDK-DL-023 | P0 | 无效 / 已撤销的 Key | 错误字符串或已 revoke 的 `pxa_` Key | 调用 `download()` | 抛 `PrismaxAuthError`；本地无业务文件（或仅空目录） |
| SDK-DL-024 | P0 | 使用他人 Key 下载对方 Package | 非包所有者账号的 `pxa_` Key + 包所有者账号的 `package_id` | 调用 `download()` | 抛 `PrismaxAuthError`（403，`package does not belong to this API key`）；非包所有者账号无新 download 记录；包所有者账号下载计数不变 |
| SDK-DL-025 | P0 | 不存在的 package_id | 合法 `pxa_` Key | `download("pkg_not_exist", out)` | 抛 `PrismaxAuthError`（403，`package not found`）；响应中不含任何文件 URL |
| SDK-DL-026 | P1 | INACTIVE Package | Package 状态非 ACTIVE | 调用 `download()` | 抛 `PrismaxApiError`（400，`package is not active`） |
| SDK-DL-027 | P1 | 无 Episode 的空 Package | Package 无 episode 映射 | 调用 `download()` | 抛 `PrismaxApiError`（400，`package has no episodes`） |
| SDK-DL-028 | P0 | Membership 失效，Key 仍 ACTIVE | 会员失效账号；记录 `last_used_at` 当前值 | 调用 `download()` | 抛 `PrismaxAuthError`（403）；`last_used_at` 不更新 |
| SDK-DL-029 | P0 | 月额度不足 | 额度已满账号；Package 含未授权新 Episode | 调用 `download()` | 抛 `PrismaxApiError`（402）；本地无业务文件；`used_episodes` 不超卖 |
| SDK-DL-030 | P1 | Package 内 Episode 均已在 My Data 中（额度已授权） | Package 内所有 Episode 的 `quota_authorized_at` 非空 | 调用 `download()` | Session 创建成功；`used_episodes` 不因本次下载增加；文件正常下载 |
| SDK-DL-031 | P1 | 同一 Package 连续两次下载 | 包所有者账号；额度充足 | 连续调用两次 `download()` | 两次均可拉取文件；各自生成独立 Session/history 记录（SDK 无幂等头，对照 R08 确认是否符合产品预期） |

### 5.5 失败恢复与非功能

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SDK-DL-032 | P0 | Session 成功但某个文件 CDN 下载失败 | 通过代理或错误 URL 模拟单文件 5xx | 调用 `download()` | 抛 `PrismaxApiError`，错误信息含失败文件的 `relative_path`；查后端 `data_downloads` 确认记账状态（对照 R04） |
| SDK-DL-033 | P1 | 重试成功 | 前两次请求失败，第三次成功 | `retries=3` 下调用 `download()` | 最终文件完整；stderr 可观察到重试行为 |
| SDK-DL-034 | P1 | 半文件残留后重新下载 | 下载中途杀进程或断网 | 检查 output 目录；再次下载 | 中断后存在截断/空文件；再次成功下载后该路径被完整文件覆盖 |
| SDK-DL-035 | P1 | 并发度对结果无影响 | 多文件 Package | 分别用 `--concurrency 1` 和默认 `5` 各下载一次 | 文件集合完全一致；并发 5 更快，无文件缺失或内容串扰 |
| SDK-DL-036 | P1 | 单文件超时触发重试 | 大 mcap 文件；`--timeout 1` | 调用 `download()` | 超时后按 `retries` 次数重试；不出现无限挂起 |
| SDK-DL-037 | P2 | 非法 `relative_path` — 路径穿越（可用 mock） | mock Session 返回 `../etc/passwd` 或绝对路径 | 调用 `_download_items()` / `download()` | 抛 `PrismaxValidationError`；不向 output 目录外写入任何文件 |
| SDK-DL-038 | P2 | 重复 `relative_path`（可用 mock） | mock Session 中两个 asset 的 `relative_path` 相同 | 调用解析逻辑 | 抛 `PrismaxValidationError: Download session contains duplicate path` |

### 5.6 上传回归

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SDK-DL-039 | P0 | 上传使用 `PRISMAX_UPLOAD_API_KEY` | 有效 `pxu_` Key；同时存在 `pxa_` Key | 不传 `api_key`，调用 `prismax.status(upload_id)` 或 `recent_uploads()` | 请求头使用 `pxu_`；`pxa_` 不出现在上传相关请求中 |
| SDK-DL-040 | P0 | 旧 `PRISMAX_API_KEY` 不能用于上传（breaking change） | 只设 `PRISMAX_API_KEY=pxu_...`；不设 `PRISMAX_UPLOAD_API_KEY` | 调用 `recent_uploads()` / `upload()` | 抛 `PrismaxAuthError`，提示设置 `PRISMAX_UPLOAD_API_KEY`；发版说明须覆盖此变更 |
| SDK-DL-041 | P1 | 上传 CLI 子命令不受 download 影响 | 已有小数据集上传记录 | `prismax scenarios`、`prismax uploads --limit 1` | 行为与本次改动前一致（在新环境变量名下） |
| SDK-DL-042 | P1 | 版本标识正确 | 已安装当前包 | 检查 `prismax.__version__` 和请求 User-Agent | `__version__` 为 `0.3.0b1`；User-Agent 为 `prismax-sdk/0.3.0b1` |

---

## 6. 建议执行顺序

1. **SDK-DL-003 / 040**：优先确认 breaking change，防止旧环境变量干扰后续验证。
2. **SDK-DL-001 / 004 / 005 / 009 / 010 / 017 / 019**：Key 隔离 + P0 Happy Path + 目录结构 + Cookie 有效性。
3. **SDK-DL-024 / 028 / 029**：跨账号权限、会员失效、额度超限。
4. **SDK-DL-020 / 022 / 031 / 032**：文件完整性、MD5 抽查、重复下载记账、Session 成功但传输失败。
5. **SDK-DL-033 ~ 038**：重试机制、半文件、并发、路径安全。
6. **SDK-DL-039 ~ 042**：上传回归验证。

---

## 7. Beta / Production Smoke

在 beta 环境（SDK 默认 `base_url` 已指向 beta pipeline）用专用测试账号执行：

```bash
export PRISMAX_DOWNLOAD_API_KEY=pxa_...
prismax download <ACTIVE package_id> --output /tmp/prismax-sdk-dl-smoke --no-progress
```

验证：退出码 0；目录含 mcap 和三路主视频。

```bash
prismax uploads --limit 1
```

验证：上传列表正常返回（确认上传未受影响）。

> 不要使用生产真实客户 Key 做破坏性操作（超额、撤销等）。

---

## 8. 单元测试补充建议

`tests/test_download.py` 建议补充以下场景（无需真实 CDN）：

| 场景 | 对应风险 |
| --- | --- |
| 空 / 空白 `package_id` | R02 |
| `relative_path` 含 `..` 或为绝对路径 | R06 / 路径穿越 |
| 两个 asset 的 `relative_path` 相同 | 重复路径 |
| asset 缺 `cookie_header` 或 `url` | R03 |
| `samples` 为空列表 | 空 Session |
| 设置 `PRISMAX_API_KEY` 但不设 `PRISMAX_UPLOAD_API_KEY` / `PRISMAX_DOWNLOAD_API_KEY`，确认各自报 AuthError | R01 |
