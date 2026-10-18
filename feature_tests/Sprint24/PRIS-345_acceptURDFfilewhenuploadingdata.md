# PRIS-345 Accept URDF file when uploading data

> 分析日期：2026-09-19（UTC+8）  
> 范围：三仓联动。Web Upload、pipeline session、Upload SDK。每条 episode **0 或 1** 个 URDF，可选，失败不挡主数据。  
> Git 提交时间为 EDT `-0400`，对应北京时间 **2026-09-19 06:21**。  
> **只测最终态。** 三仓同一作者、同一时刻落地，必须一起发。

| 仓库 | 最终 Commit | 说明 |
| --- | --- | --- |
| `app-prismax-rp` | `30ca62a` *feat: upload optional episode URDFs without changing worker manifests* | Web 校验 / PUT 容错 / worker manifest 排除 URDF；API 示例脚本多拉 `assets.urdf` |
| `app-prismax-rp-backend` | `6ef7d24` *feat: support optional per-episode URDF uploads and downloads* | session 签名与落库、resume 不因 URDF 重跑 worker、下载计入 file limit |
| `sdk-vla-foundry` | `2113157` *feat: support optional per-episode URDF upload and download* | 扫描、DataUpload 映射、PUT 容错、download 拉 URDF。本地 `testing` 若停在 `57fb7e4` 需 `git fetch` |

同日 backend 另有 `53a447f`（PRIS-335 `qa_score` 进 downloadable uploads API），**不在本 feature 范围**。

依赖：先执行 `app_prismax_data_pipeline/sql/20260918_episode_urdf.sql`，再发 pipeline。列可空，历史 episode 不用回填。

---

## 1. Feature 描述

上传 robotics data 时，每个 episode 可以附带 **一个** `.urdf`。它只做原样搬运：不进 worker manifest、不解析 XML、不打包 mesh/texture、不参与 episode 成败判定。没有则跳过；传失败只警告并继续。

| 项目 | 规则 |
| --- | --- |
| 数量 | 每 episode 0 或 1 个；没有 upload 级默认 URDF，没有独立 asset 表 |
| 路径 | 必须 `{episode_key}/{original_filename}.urdf`，且 `episode_key` 已由 `.mcap` 存在 |
| 存储 | GCS `raw/{upload_id}/{episode_key}/{original_filename}.urdf`；`data_episodes.raw_urdf_path` |
| Worker / QA / 状态机 | 不变。manifest 不含 URDF |
| 传输失败 | 仅 URDF：客户端 warn + continue；MCAP/MP4 失败仍整单失败 |
| 目录 / 详情 UI | **不展示、不预览** URDF。chip 仍只计 MCAP/video |
| 下载 | 对象真实存在才带 `assets.urdf`；相对路径 `{episode_id}/{filename}.urdf` |

**不在本次范围：**

- 解析 URDF、校验 mesh、可视化预览
- 完成后单独补传 / repair URDF
- 非 `mcap/mp4` 格式
- 目录页、Episode 详情、QA Review 增加 URDF 控件

---

## 2. 最终产品规则（`30ca62a` / `6ef7d24` / `2113157`）

```text
Web 选文件 / SDK scan 或 DataUpload spec
  → 合法：{episode}.mcap + {episode}/*.mp4（≥3，含 env/left/right）
           + 可选 {episode}/{name}.urdf（恰好 0 或 1）
  → 非法：根目录 robot.urdf、子目录 a/meshes/robot.urdf、
           两个 urdf、未知 episode 的 urdf、.URDF 大写后缀
  → URDF 不创造 episode（backend）；Web 校验里单独 urdf 文件夹会当成残缺 episode 报错

Create session  POST /data/upload-sessions  与  /v1/data/upload-sessions
  → 给 URDF 签 PUT URL
  → UPDATE data_episodes.raw_urdf_path（create 时就写，即使之后 PUT 失败）
  → 返回的 worker 文件列表仍不含 URDF

PUT 到 signed URL
  → .urdf HTTP/网络失败：Web `uploadRawFile` / SDK `PrismaXClient.upload_files` 跳过
  → 其它文件失败：整次上传失败

Resume（仅 status=UPLOADING）
  → 缺 URDF：missing_files 只有该 urdf；不把 _MANIFEST.json 算进去，不重触发 worker
  → 缺视频/mcap：仍会补 manifest
  → resume payload 不带 urdf：不 UPDATE，保留已有 raw_urdf_path
  → 已完成 upload：没有 repair 接口

Download（browser / generated script / API session / SDK）
  → 有 raw_urdf_path 且 blob 存在 → assets.urdf
  → 列为 NULL 或对象不存在 → 省略，不当成下载失败
  → 存储鉴权/服务错误 → 向上抛，不当成“没有 URDF”
  → 目录预估文件数仍是 MCAP/video；真正下载会把存在的 URDF 算进 max_files
```

---

## 3. Episode 文件夹格式

Web 选目录、SDK 扫目录、后端校验，用的是**同一套相对路径**。一次 upload 的根目录里：`.mcap` 平铺在根上，视频和可选 URDF 放在**同名文件夹**里，且只能再深一层。

```text
选中的根目录/                  ← Web 拖进来的那一层；SDK scan 的 root
  1.mcap                       ← 必填。文件名去掉 .mcap 就是 episode_key
  1/                           ← 必须与 1.mcap 同名
    high.mp4                   ← 至少 3 个 mp4；要能分出 env/high、left、right
    left.mp4
    right.mp4
    high2.mp4                  ← 可选，额外镜头
    robot.urdf                 ← 可选，最多 1 个；文件名随意，扩展名必须小写 .urdf

  2.mcap                       ← 第二个 episode
  2/
    high.mp4
    left.mp4
    right.mp4                  ← 这个 episode 可以没有 URDF
```

对应到接口里的 `relative_path`：

| 本地位置 | `relative_path` | 角色 |
| --- | --- | --- |
| 根/`1.mcap` | `1.mcap` | 定义 episode `1` |
| 根/`1/high.mp4` | `1/high.mp4` | 视频，必须直接在 `1/` 下 |
| 根/`1/robot.urdf` | `1/robot.urdf` | 可选 URDF |

三条硬规则：

1. **两层路径。** 只允许 `{episode_key}/{filename}`。`1/meshes/robot.urdf` 不行。
2. **根目录只能放 `.mcap`。** `robot.urdf` 不能和 mcap 放在同一层。
3. **URDF 不能单独开 episode。** 没有 `1.mcap` 就不能有 `1/robot.urdf`。文件夹名必须等于 mcap 的 stem。

主视频怎么认（URDF 不参与）：文件名含 `left` → left；含 `right` → right；两个都不含 → env/high。精确名 `high.mp4` / `left.mp4` / `right.mp4` 优先于 `high2.mp4` 等。

**SDK 例外：** 采集软件如果把一切都丢在 `30361/` 里（mcap 也在子文件夹），Web 扫目录会失败。要用 `DataUpload` 的 `file_layout` / `assets` 把源文件**映射**成上面这套 `relative_path`，远端存储仍是 `30361.mcap` + `30361/high.mp4` + `30361/xxx.urdf`。

---

## 4. 路径与校验（三端对齐）

合法例子：`a.mcap`、`a/high.mp4`、`a/left.mp4`、`a/right.mp4`、`a/robot.urdf`。

| 输入 | Web `validateMcapMp4` | SDK `validate_mcap_mp4` / DataUpload | Backend `_extract_urdf_paths` |
| --- | --- | --- | --- |
| `a/robot.urdf` 且已有 episode `a` | 通过 | 通过 | 通过，记录 path |
| 无 URDF | 通过 | 通过 | 不 UPDATE |
| `a/one.urdf` + `a/two.urdf` | `at most one .urdf` | 同 | ValueError 同文案 |
| `robot.urdf`（根目录） | 错误（根只允许 .mcap） | 同 | ValueError：必须 `{episode_key}/{filename}.urdf` |
| `a/meshes/robot.urdf` | Nested folders not allowed | 同 | 路径段数 ≠ 2 |
| `unknown/robot.urdf`（无 unknown.mcap） | 当成残缺 episode（缺 mcap） | 同 | episode_key 不在已有 keys |
| `a/robot.URDF` | 当非法扩展名（`endsWith('.urdf')` 区分大小写） | 同 | `lower().endswith` 命中后再要求精确 `.urdf` → ValueError |
| 只有 URDF、没有 mcap | 报缺 mcap | 同 | URDF **不会**创建 episode |

SDK **额外能力（Web 没有）：**

- `DataUpload` templated / explicit 的 `file_layout.urdf` / `assets.urdf`：把任意源路径映射成 `{episode_key}/{源文件名}.urdf`，不必先摆成标准树。
- 同一份本地 URDF 可以映射到多个 episode，各存一份（`a/shared.urdf`、`b/shared.urdf`）。非 URDF 源文件仍禁止一对多。
- spec 里声明了 `urdf` 则加载时源文件必须存在；**只有传输失败才是 optional**。缺文件 → `PrismaxValidationError`。

Web 统计条（Episodes / MCAP / Videos）**不单独计 URDF**；Total 字节含 URDF。

---

## 5. 上传与 Resume

Web：`src/components/Data/uploadFiles.js`。`buildManifestPayload` 过滤 `.urdf`。`uploadRawFile` 对 URDF 的非 2xx / 网络错误 `console.warn` 后返回 `false`。

SDK：`prismax/manifest.py` 同样排除；`client.py` 捕获 `PrismaxApiError`，CLI 进度打 `skipped (optional upload failed)`。

Backend create（Web `/data/upload-sessions`、SDK `/v1/data/upload-sessions`）：

- `episode_count` 仍只由 mcap 决定。
- `signed_urls` 含 `raw/{upload_id}/{episode_key}/{filename}.urdf`。
- 立刻 `SET raw_urdf_path`。因此 **DB 路径可能指向尚未成功 PUT 的对象**；下载侧用 blob exists 纠偏。

Resume：缺 URDF 时 `missing_files = ["a/robot.urdf"]`，**不含** `a/_MANIFEST.json`。缺 `a/high.mp4` 时才是 `["a/_MANIFEST.json", "a/high.mp4"]`。Web 与 `/v1/` 两条 resume 行为一致。

没有 completed 后的 URDF 补传接口。

---

## 6. 下载

对象存在时：

| 字段 | 值 |
| --- | --- |
| `assets.urdf.relative_path` | `{episode_id}/{original_filename}.urdf` |
| `assets.urdf.download_name` | `{episode_id}_{original_filename}.urdf`（浏览器 attachment） |
| CDN cookie | 绑到该 URDF object；tracking 含 `asset=urdf` |
| `total_bytes` | 加上 URDF size |

浏览器前端实际保存名走 `buildBrowserDownloadFileName` / `fileNameForDownload`：非 mcap 用 `{episode_key}_{basename}`（例如 `a_robot.urdf`），与 backend `download_name` 的 `episode_id` 前缀可能不一致。验重名冲突时以 **相对路径里的 episode_id 目录** 和 SDK 落盘路径为准。

SDK / 生成脚本：按 `relative_path` 落到 `{episode_id}/robot.urdf`，不同 upload 同名 URDF 不会互相覆盖。

API 示例 `apiPackageExample.js` 的循环 key 已加入 `"urdf"`。

目录页文件数仍是预估（MCAP+video）。`_prepare_download_payload` 的 `max_files`（默认 manifest 800）**含** URDF。接近上限时，带 URDF 的包可能比目录显示的更早触发 limit。

缺对象：省略 `assets.urdf`，下载其余文件。GCS `PermissionError` 等不得被当成缺失。

Worker metadata 完整与 GCS fallback 两条 CDN 组装路径都要挂 URDF。

---

## 7. 风险点

| 编号 | 风险 | 优先级 | 验证重点 |
| --- | --- | --- | --- |
| R-01 | URDF 失败拖垮整次上传 | 高 | 断网/4xx 只跳过 URDF；mcap/mp4 仍成功；episode 能进后续处理 |
| R-02 | URDF 进 worker manifest | 高 | 上传后 GCS 无 `{episode}/_MANIFEST.json` 内的 urdf；处理流水线与无 URDF 一致 |
| R-03 | 非法布局被收下 | 高 | 双 urdf、根目录、嵌套、大写 `.URDF`、无主 episode 的 urdf，Web/SDK/API 都拒绝 |
| R-04 | Resume 因 URDF 重跑 worker | 高 | 只缺 URDF 时 missing 不含 manifest；只缺视频时仍补 manifest |
| R-05 | 路径已写、对象没有 | 高 | PUT 失败后 `raw_urdf_path` 可能非空；下载不得 500，应省略 URDF |
| R-06 | 同名 URDF 覆盖 | 高 | 两个 upload 都叫 `robot.urdf`，SDK/脚本落到不同 `{episode_id}/` |
| R-07 | 文件数上限被 URDF 挤爆 | 中 | 目录显示未超、实际带 URDF 后超过 `max_files` 应失败并 mark download failed |
| R-08 | 存储错误被当成无文件 | 高 | mock/制造权限错误时接口失败，而不是静默无 urdf |
| R-09 | 未跑 migration 就发 pipeline | 高 | 查询 `e.raw_urdf_path` 会炸；必须先 `20260918_episode_urdf.sql` |
| R-10 | SDK 与 Web 能力差 | 中 | 扁平目录 + 共享 URDF 只走 SDK；Web 必须每 episode 文件夹各放一份 |
| R-11 | 目录 UI 看起来像没带上 | 低 | 详情/chip 无 URDF 是设计如此；用 DB + 下载 payload 确认 |
| R-12 | 完成后无法补传 | 中 | SUCCEEDED/FAILED 后再带 urdf resume 必须失败；文档已声明无 repair |

---

## 8. 测试数据与环境

- 三仓含上表 commit；`data_episodes.raw_urdf_path` 已加。
- 最小合法包：1 mcap + high/left/right mp4 + 可选 `robot.urdf`（任意合法 XML 文本即可，不校验内容）。
- 混合包：episode `a` 有 URDF，episode `b` 没有。
- 两套 upload 使用相同 `robot.urdf` 文件名，用于下载防覆盖。
- Operator（Web token）+ Upload API key（SDK）。
- 有 download membership 的账号，走 Browse / My Data / `POST /v1/data/download-sessions`。
- 一个仍为 `UPLOADING` 的 session，用于 resume。
- 桌面 Chrome；可看 Network、GCS `raw/`、DB。
- SDK 测前确认 `origin/testing` 含 `2113157`。

### 8.1 已跑 SDK 样本（beta，2026-09-21）

账号：`RM11010325010333`，`task_id=12`（Test E-commerce Warehouse）。SDK `2113157`。

| 用例 | Upload ID | 本地数据 | 说明 |
| --- | --- | --- | --- |
| PRIS-345-014 | **1977** | `~/Desktop/Upload_Testing/flat_11546` | 扁平 templated；远端 `11546/11546.urdf` |
| PRIS-345-015 | **1978** | `~/Desktop/Upload_Testing/mixurdf` | explicit；仅 `11546` 有 URDF，`hang_clothes` 无 |
| PRIS-345-016 | **1979** | `~/Desktop/Upload_Testing/sharedurdf` | 共享源；本地一份 `11546/11546.urdf` → 远端两份 |
| PRIS-345-017 | **无**（未建 session） | `~/Desktop/Upload_Testing/error_spec` | spec 声明 `11546/11546.urdf`，磁盘无此文件；`PrismaxValidationError` |

后续下载 / worker / QA（026、029、030、036）可用这三条，对照 `#1978` 的无 URDF episode 与 `#1979` 的双 path。

---

## 9. E2E 测试用例

### 9.1 Web 上传校验与传输

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-345-001 | P0 | 带一份 URDF 上传 | operator，合法 task/machine | 选择 `a.mcap` + `a/` 下 3 路 mp4 + `a/robot.urdf`，创建并传完 | session 成功；GCS 有 `raw/{id}/a/robot.urdf`；DB `raw_urdf_path` 对应该 key；episode 数仍为 1 |
| PRIS-345-002 | P0 | 不带 URDF 回归 | 同上，无 urdf | 仅 mcap+mp4 上传 | 与改前一致；`raw_urdf_path` NULL；后续处理不报错 |
| PRIS-345-003 | P0 | 混合 episode | `a` 有 urdf，`b` 无 | 一次选中两套 | 两 episode 都创建；只有 `a` 有 path；manifest 两边都无 urdf |
| PRIS-345-004 | P0 | 每 episode 最多一个 | `a/one.urdf` 与 `a/two.urdf` | 选文件 | 前端错误 `Episode a may contain at most one .urdf file.`；不创建 session |
| PRIS-345-005 | P0 | 根目录 URDF | `robot.urdf` 与合法 episode | 选文件 | 拒绝（根只允许 .mcap）；不创建 session |
| PRIS-345-006 | P0 | 嵌套 URDF | `a/meshes/robot.urdf` | 选文件 | Nested folders not allowed |
| PRIS-345-007 | P1 | 大写扩展名 | `a/robot.URDF` | 选文件 | 拒绝 |
| PRIS-345-008 | P1 | 无主 episode 的 URDF | 只有 `unknown/robot.urdf` 或对不上 mcap | 选文件 | 报缺 mcap / 非法 episode，不创建 |
| PRIS-345-009 | P0 | URDF PUT 失败可继续 | 合法包；拦截 `robot.urdf` 的 PUT 返回 403 或断网 | 继续传完其它文件 | 上传完成；console 有 Optional URDF upload failed；mcap/mp4 在桶内 |
| PRIS-345-010 | P0 | 必传文件失败仍失败 | 拦截 `a/high.mp4` PUT | 上传 | 整次失败，不把 URDF 失败策略套到视频上 |
| PRIS-345-011 | P1 | 统计条 | 含 urdf 的包 | 看 Upload Session meta | Episodes/MCAP/Videos 不含单独 URDF 计数；Total 含 urdf 字节 |
| PRIS-345-012 | P1 | 无新 UI | 打开 Upload / Dashboard / Episode 详情 | 浏览 | 无 URDF 预览、无必填 URDF 控件 |

### 9.2 SDK 上传

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-345-013 | P0 | 标准目录扫描 | `{a.mcap, a/high,left,right.mp4, a/robot.urdf}` | `scan` / CLI 上传该文件夹 | 校验通过；远端 path `a/robot.urdf`；manifest 4 个非 urdf 文件 |
| PRIS-345-014 | P0 | 扁平目录 templated | `flat_11546/`：`11546.mcap`、`11546_cam_*.mp4`、`11546.urdf` 全在根上 | templated `prismax_upload.json` + `create_upload_session(..., task_id=12)` | **Upload #1977**。映射 `11546.mcap`、`11546/high\|left\|right.mp4`、`11546/11546.urdf`；manifest 不含 urdf；5/5 PUT |
| PRIS-345-015 | P0 | explicit 部分 episode 无 URDF | `mixurdf/`：`11546` 有 urdf，`hang_clothes` 无 | explicit JSON，只给 11546 写 `assets.urdf` | **Upload #1978**。9/9；仅 `11546/11546.urdf`；`hang_clothes` 无 urdf；两边 manifest 都只有 mcap+3mp4 |
| PRIS-345-016 | P1 | 共享源 URDF | `sharedurdf/`：磁盘只有 `11546/11546.urdf` | explicit 两段 `assets.urdf` 都指向该文件（视频名不同，不能 templated） | **Upload #1979**。10/10；远端 `11546/11546.urdf` 与 `hang_clothes/11546.urdf`；本地源路径相同；manifest 仍不含 urdf |
| PRIS-345-017 | P0 | spec 声明但文件缺失 | `error_spec/`：有 mcap+3mp4，**没有** urdf；JSON 仍写 `urdf.source_path` | `DataUpload.from_json` / `prismax upload-data` | **无 Upload ID**。`PrismaxValidationError: episode 11546 urdf does not exist: .../error_spec/11546/11546.urdf`；CLI exit 1；未调 create session |
| PRIS-345-018 | P0 | SDK URDF 传输失败 | mock/拦截 URDF PUT | `upload_session` | warning + `skipped (optional upload failed)`；视频传完 |
| PRIS-345-019 | P1 | 非法扫描 | 双 urdf / 根 urdf / `.URDF` | `validate_mcap_mp4` | 非空 errors，与 Web 同语义 |

### 9.3 Resume 与后端 session

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-345-020 | P0 | Web/API create 签名 | operator 或 API key | POST 带 `a/robot.urdf` | 200/201；`signed_urls` 含 `raw/{id}/a/robot.urdf`；DB 已写 path |
| PRIS-345-021 | P0 | Resume 只缺 URDF | UPLOADING，桶内已有 mcap/mp4/manifest，无 urdf | POST `.../resume` 文件列表含 urdf | 200；`missing_files` 仅为 `a/robot.urdf`；不要求重传 `_MANIFEST.json` |
| PRIS-345-022 | P0 | Resume 缺视频 | 同上但缺 `a/high.mp4` | resume | missing 含 manifest 与该 mp4 |
| PRIS-345-023 | P0 | Resume 省略 URDF | 已有 `raw_urdf_path` | resume files 不含 urdf | 不把 path 打成 NULL |
| PRIS-345-024 | P1 | 完成后不能补 | upload 已非 UPLOADING | 再 resume 带 urdf | 按原 resume 规则拒绝；无新 repair API（404/原错误） |
| PRIS-345-025 | P1 | 双路由一致 | 同一套 files | `/data/upload-sessions` 与 `/v1/data/upload-sessions` 及对应 resume | 校验、签名、missing 行为一致（HTTP 201 vs 200 除外） |

### 9.4 下载

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-345-026 | P0 | Browser 含 URDF | membership；样本 **#1977** / **#1979** 的 11546 | Browse 或 My Data 直接下载该 episode | `files` 含 urdf；字节合计含 urdf；能下到内容与上传一致 |
| PRIS-345-027 | P0 | Browser 无 URDF / 对象缺失 | **#1978** 的 `hang_clothes`（path NULL）；或 path 有但 blob 无 | 下载 | 其余文件成功；payload 无 `assets.urdf`；不报整包失败 |
| PRIS-345-028 | P0 | 生成脚本 / manifest | 有 URDF 的 episode | 下 manifest 并跑脚本 | 脚本遍历含 urdf；落到带 episode 隔离的路径 |
| PRIS-345-029 | P0 | API session + SDK download | Download API key，package 含带 URDF 的 sample | `download-sessions` 再 SDK/`prismax download` | sample.assets.urdf 有 url；cookie 前缀指向该 object；`asset=urdf`；落盘 `{episode_id}/{filename}.urdf` |
| PRIS-345-030 | P0 | 同名不覆盖 | **#1979** 两个 episode 远端都叫 `11546.urdf`；也可再加 **#1977** | 一次下两个 episode | 两个目标文件共存（不同 `episode_id` 目录） |
| PRIS-345-031 | P0 | API 示例脚本 | 打开 Robotic Data 的 API package 示例 | 看生成代码 | 循环 key 含 `"urdf"` |
| PRIS-345-032 | P1 | 文件上限含 URDF | 人为把 max_files 收到「mcap+3video」 | 请求带 URDF 的 manifest/browser 下载 | 触发 `limited to N files`；download 记失败 |
| PRIS-345-033 | P1 | 目录预估不含 URDF | 同一 episode | 看目录文件数 vs 实际 files.length | UI chip 仍是 mcap/video；实际下载多 1 个文件 |
| PRIS-345-034 | P1 | CDN 两条组装 | metadata 完整 与 不完整（GCS fallback） | 打 API download session | 两种都有 urdf（对象存在时）；cookie 作用域是该 URDF |
| PRIS-345-035 | P1 | 无 URDF 的旧 episode | migration 前数据，列为 NULL | 下载 | 行为与改前一致 |

### 9.5 跨功能 / 负向

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| PRIS-345-036 | P0 | Worker / QA 不受影响 | 跟 **#1977 / #1978 / #1979** 直到处理完、进 QA | 状态迁移、视频转码、QA 队列与无 URDF 相同；worker 输出 metadata 无 urdf 字段也正常 |
| PRIS-345-037 | P1 | 非法 API 直打 | 跳过前端，POST 双 urdf 或 `.URDF` | 4xx，不写脏 path |
| PRIS-345-038 | P2 | URDF 内容不校验 | 上传非 XML 的 `.urdf` 文本 | 接受并原样存、原样下；不解析 mesh |
| PRIS-345-039 | P1 | Jobs / Order 上传 | 从 Assigned Jobs 走 Web 或 SDK 带 urdf | 与普通 task 相同的可选规则 |
| PRIS-345-040 | P2 | 回滚顺序 | 先回滚应用再留列 | 旧代码不读该列可跑；禁止先 drop 列再留新代码 |

---

## 10. 发布前检查清单

- [ ] SQL `20260918_episode_urdf.sql` 已在目标库执行
- [ ] 三仓一起发：frontend `30ca62a`、pipeline `6ef7d24`、SDK `2113157`（含 README 扁平目录示例）
- [ ] 无新 bucket / 无 worker 发版需求
- [ ] 所有 P0：可选、单文件、失败不阻断、manifest 不含 URDF、resume 不误触发 worker、下载按对象存在性附加、同名隔离
- [ ] 单测（环境允许）：
  - frontend `src/components/Data/uploadFiles.test.js`
  - backend `PYTHONPATH=.:app_prismax_data_pipeline .venv/bin/python -m unittest app_prismax_data_pipeline.test_episode_urdf`
  - SDK `tests/test_urdf.py`（需在含 `2113157` 的树）

---

## 11. 已知限制

1. URDF 不进目录 / Episode 详情 / QA UI，验收只能看 GCS、DB、下载 payload。
2. 客户端 PUT 失败后 `raw_urdf_path` 仍可能已写入；下载靠 blob exists 省略，没有自动清列。
3. 完成后不能补传 URDF。
4. 不打包 URDF 引用的 mesh / texture。
5. Web 不能把根目录共享 URDF 映射到多 episode；只能 SDK spec。
6. 浏览器保存文件名可能用 `episode_key` 前缀，backend `download_name` 用 `episode_id`；防覆盖看 `relative_path`。
7. 扩展名必须小写 `.urdf`。
8. 目录文件数预估不含 URDF，真实下载 limit 含 URDF。

---

## 12. 关联说明

- 设计说明：`app-prismax-rp-backend/app_prismax_data_pipeline/URDF.md`。
- PRIS-335 `53a447f` 同属 9/19 UTC+8 的 backend commit，测 downloadable 列表分数时不要和 URDF 文件数混为一谈。
- 可视化用的 `prismax-python` URDF 渲染是另一条产品线，本 feature 只做上传搬运。
