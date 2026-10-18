# SDK_0.2.1_Fix_Repeated_Episode_Uploads

> 分析日期：2026-08-07  
> 仓库：`sdk-vla-foundry`  
> 分支：`codex/fix-episode-upload-cache`  
> 提交：`e3fe640` — Fix repeated episode uploads  
> 版本：`0.2.0` → `0.2.1`  
> 影响文件：`prismax/data_upload.py`、`prismax/upload.py`、`README.md`、`tests/test_data_upload.py`

---

## 0. 背景说明（0.2.0 性能根因）

**一句话：0.2.0 里每传完一集就把本地 session 扔掉了，下一集又得对整批文件重新 `resume`，所以一集的耗时被整批声明文件数拖死，而不是被这一集自己要传的数据拖死。**

### 本来应该怎样

1. `create_upload_session`（`upload.py`）把整批文件（例如 399 集、1995 个文件）的 session 存进内存，并拿到 signed URL。  
2. 之后每调一次 `upload_episode()`，本应走 `_get_or_resume_data_session`：缓存还在且未过期 → **直接复用**，只 PUT 这一集的文件。  
3. `_session_urls_are_fresh`（过期前 5 分钟内会刷新）也是为这个缓存准备的。

### 0.2.0 实际怎样

`upload_episode()` 无论成败，`finally` 里都会无条件：

```python
finally:
    data_upload._discard_session(upload_id)  # upload.py:221
```

也就是**每次传完一集就清空整份 session**。下一集再进 `_get_or_resume_data_session`（`upload.py:543`）时缓存永远是空的，于是只能再调：

`POST /v1/data/upload-sessions/{id}/resume`

并把**整批**已声明文件再报一遍。后端再给所有「还没传完」的文件重新签发 signed URL。缓存与过期检查其实早就写好了，但被无条件 `_discard_session` 废掉了——整批里缓存只能用上「第一次」。

### 实测（399-episode batch）

| 数字 | 含义 |
| --- | --- |
| 399 集 / 1995 声明文件 | 一批很大 |
| 每集约 93.5 s | 大部分时间不在传数据 |
| 其中 ~4 s / 211 MB PUT（约 53 MB/s） | 真正上传只要几秒 |
| py-spy 45 次采样里 44 次卡在 `resume_upload_session` | CPU 基本在等 resume API |
| 每集约时从 106 s → 91 s（剩余文件 1995 → ~1470） | 越传越快，是因为 resume 要处理的「未传完文件」变少了 |
| 约 29 ms × 剩余声明文件数 | 每次 resume 按「声明文件数」计费，**每集都付一遍** |

因此：**单集耗时 ≈ 整批剩余文件数 × API 延迟**，而不是 ≈ 这一集体积。

### 与本修复的关系

`e3fe640` / `0.2.1` 改成：成功后只剔除该 episode 的 signed URL（`_discard_session_episode_urls`），**保留 session** 给后续 episode；失败路径才整份 `_discard_session`。配合已有的 `_session_urls_are_fresh`，顺序多集上传才能真正复用缓存（除非快过期才 resume）。

---

## 1. 问题与修复目标

修复同一进程、同一 `DataUpload` 对象上**重复调用 `upload_episode()`** 时的行为：

| 场景 | 修复前风险（推断） | 修复后行为 |
| --- | --- | --- |
| Episode 已成功上传，再次 `upload_episode` | 可能再次走上传 / 误用缓存 signed URL | **本地跳过**，返回 `skipped=True, reason=already_completed`，不调后端 resume、不重传文件 |
| Episode 曾失败，再次 `upload_episode` | 可能用失效/不完整的本地 session 重试 | **直接拒绝**，要求显式 `resume_upload()` |
| 多 Episode 顺序上传 | 每完成一个可能整份丢弃 session，导致下一集反复 resume | 成功后只剔除该 episode 的 signed URL，**保留 session** 给后续 episode |
| 并发 cache miss 同时 resume | 可能打出多次 `resume_upload_session` | 按 `upload_id` 加锁，**合并为一次** resume |

状态只存在于**当前进程内存**中的 `DataUpload` 对象；换进程 / 新建 `DataUpload` 不会继承 `completed` / `incomplete`。

---

## 2. 核心状态机

状态以 token `(upload_id, episode_key)` 为键（旧实现只用 `episode_key`，同名 episode 跨不同 `upload_id` 会误冲突）。

### 2.1 字段

| 字段 | 含义 |
| --- | --- |
| `_active_episode_keys` | 正在上传中的 token 集合；并发同 episode 会报错 |
| `_episode_upload_states` | token → `"completed"` / `"incomplete"` |
| `_sessions` | `upload_id` → 本地缓存的 session（含 `signed_urls`） |
| `_session_refresh_locks` | 每个 `upload_id` 一把锁，保护 session refresh / resume |

### 2.2 `upload_episode` 状态流转

```
_begin_episode_upload(upload_id, episode_key)
        │
        ├─ token 已在 active     → PrismaxValidationError（正在上传）
        ├─ state == completed    → 立即返回 skipped / already_completed
        ├─ state == incomplete   → PrismaxValidationError（要求 resume_upload）
        └─ 无 state              → 加入 active，返回 "started"
                │
                ▼
        构建 client + _get_or_resume_data_session
                │
        ┌───────┴───────────────────────────────┐
        │ 上传成功                              │ 上传失败（已拿到 session）
        │ 剔除该 episode 的 signed_urls         │ 丢弃整份 session
        │ state=completed，释放 active          │ state=incomplete，释放 active
        └───────────────────────────────────────┘
```

补充：若在拿到 session **之前**失败（`upload_started=False`），只 `_release_episode_uploads`，**不**写入 `incomplete`，允许直接再试 `upload_episode`。

### 2.3 Session / signed URL 缓存策略

1. **新鲜 session**：有缓存且未过期（`expires_at` 空视为 fresh；否则需晚于 now+5min）→ 直接复用，不调 resume。  
2. **过期 / 无缓存**：在 `_session_refresh_lock(upload_id)` 内双重检查后调用 `resume_upload_session`，再 `_store_session`。  
3. **单集成功后**：`_discard_session_episode_urls` 只删该 episode 路径（`{key}.mcap` 或 `{key}/...`），其他 episode 的 URL 仍留在缓存里，便于顺序上传。  
4. **失败后**：`_discard_session(upload_id)` 整份清掉，避免继续用半残缓存。

### 2.4 批量 API 联动

- `upload_session` / `resume_upload`：claim 改为带 `upload_id`；成功后 `_mark_episode_uploads_completed` 把**全部** declared episode 标为 `completed`。  
- 因此：`upload_session` 成功后再对其中某一集 `upload_episode` → 应被 skip。  
- `resume_upload` 成功后，失败过的 episode 变为 `completed`；再 `upload_episode` 同理会 skip。

---

## 3. 关键返回值 / API 行为变化（调用方需注意）

成功重复调用时，第二次返回形状变化：

```python
{
  "upload_id": <int>,
  "episode_key": "<key>",
  "skipped": True,
  "reason": "already_completed",
}
```

与首次成功返回的 `_public_session_result(session)`（含 `machine_id` / `task_id` 等）不同。集成方若写死解析 session 字段，需兼容 `skipped`。

失败重试路径：

- 错误信息明确提示：`Resume with prismax.resume_upload(upload_id, data_upload)`。  
- 直接再调 `upload_episode` 会得到 `PrismaxValidationError`，且文案含 `resume_upload`。

---

## 4. 单元测试覆盖（仓库已有）

提交内新增/改写的关键 要点（`tests/test_data_upload.py`）：

| 用例 | 验证点 |
| --- | --- |
| `test_sequential_episode_uploads_reuse_cached_session` | 两集顺序上传不 resume；各集只传自己的文件；结束后 `signed_urls` 为空 |
| `test_upload_episode_refreshes_expired_session_urls` | 过期 session 会 resume 一次 |
| `test_concurrent_cache_misses_share_one_resume_request` | 两线程 cache miss 只触发一次 `resume_upload_session` |
| `test_repeated_completed_episode_is_skipped_without_resume` | 完成后重复调用 skip，且不再 resume / 不重传 |
| `test_failed_episode_requires_explicit_resume_before_retry` | 失败后再 `upload_episode` 抛 ValidationError；session 被清空 |
| `test_explicit_resume_completes_previously_failed_episode` | 失败 → `resume_upload` → 再 `upload_episode` 被 skip |
| `test_same_episode_cannot_be_claimed_twice` | 同 `(upload_id, episode)` 不可并发 claim |

本地可先跑：

```bash
cd sdk-vla-foundry
python -m pytest tests/test_data_upload.py -q
```

---

## 5. QA 测试用例

按类型排序：**手工 → 回归 → 冒烟 → 集成 → 自动化 → 单元/真网**。

| ID | 优先级 | 类型 | 场景 | 步骤 | 期望结果 |
| --- | --- | --- | --- | --- | --- |
| TC-01 | P0 | 手工 / 集成 | 成功后重复 `upload_episode` 应跳过 | 1. 用合法 JSON/`DataUpload` 创建 session，得到 `upload_id`<br>2. `upload_episode(upload_id, "episode_1", data)` 成功<br>3. 同一 `data` 对象再调一次同参数 | 返回 `skipped=True`、`reason=already_completed`；无新的文件上传流量（GCS/signed URL 签发不增加）；后端 episode 状态正常，无重复完整上传异常 |
| TC-02 | P0 | 手工 / 集成 | 失败后禁止直接重试，必须 `resume_upload` | 1. 人为制造失败（断网 / 中途杀进程 / 存储 5xx），使 `upload_episode` 抛 `PrismaxApiError`<br>2. 同一 `data` 再调 `upload_episode`<br>3. 调用 `resume_upload(upload_id, data)`<br>4. 可选：再调 `upload_episode` | 步骤 2：`PrismaxValidationError`，文案含 `resume_upload`<br>步骤 3：只补传缺失文件，episode 最终完整<br>步骤 4：若已 completed 则为 skip |
| TC-12 | P2 | 回归 | 未声明 episode | 对 spec 外 `episode_key` 调用 `upload_episode` | 仍抛 `PrismaxValidationError` |
| TC-13 | P2 | 回归 | `wait` / `wait_for_upload` 路径 | `upload_session(..., wait=True)` 或 `resume_upload(..., wait=True)` 成功后，再对其中一集调 `upload_episode` | episode 已标 completed；后续调用 skip，行为与无 wait 路径一致 |
| TC-10 | P2 | 冒烟 | 错误提示与 README 一致 | 核对 README 与失败/重复调用时的异常文案 | 文档写明：同进程同对象完成后 skip；失败用 `resume_upload`；错误文案可指导用户操作 |
| TC-11 | P2 | 冒烟 | 版本与安装 | 安装该分支/版本，检查 `prismax.__version__` | 版本为 `0.2.1`，行为符合上文 |
| TC-03 | P0 | 集成 | 多 Episode 顺序上传共用缓存 | 1. Spec 含 `episode_1`、`episode_2`<br>2. 创建 session 后依次 `upload_episode` 两集（中间不新建 `DataUpload`） | 两集均成功；第二集无多余全量 resume（日志/抓包符合缓存策略）；两集文件与 manifest 均落地正确 |
| TC-04 | P0 | 集成 | `upload_session` 成功后再单集上传 | 1. `upload_session(upload_id, data)` 成功<br>2. 再对其中一集调 `upload_episode` | 单集调用被 skip（`already_completed`），无重复上传 |
| TC-07 | P1 | 集成 | 不同 `upload_id` 同名 episode | 两个 upload session 都声明 `episode_1`，分别上传（按 API 约束构造两个 `DataUpload` / 两次 create） | token 含 `upload_id`，互不误拦；各自可独立完成 |
| TC-09 | P1 | 集成 | 进程重启 / 新 `DataUpload` 实例 | 1. 进程 A 中某 episode 已上传成功<br>2. 新进程（或重新 `DataUpload.from_json`）对同一 `upload_id` 再调 `upload_episode` | 本地无 `completed` 记忆，会走真实上传路径；后端 resume 只返回缺失文件（已存在则几乎空传）；不因跨进程假 skip 漏传，也不盲目全量重传破坏数据 |
| TC-05 | P1 | 自动化优先 | 同 episode 并发上传 | 两线程同时对同一 `(upload_id, episode_key)` 调 `upload_episode` | 一方成功或进行中，另一方报 `already being uploaded`；最终只有一份有效上传，无双写损坏 |
| TC-06 | P1 | 自动化优先 | 不同 episode 并发上传 | 同 `upload_id` 下并发上传 `episode_1` 与 `episode_2` | 均可成功；同时 cache miss 时 resume 请求合并（非 N 次风暴）；两集最终完整 |
| TC-08 | P1 | 单元已有 + 真网 | Signed URL 过期 | 缓存 session 的 `expires_at` 已过期（或等待过期），再调 `upload_episode` | 自动 `resume_upload_session` 刷新后仍可上传成功 |

---

## 6. 风险与观察点

1. **Skip 仅本地**：跨进程或新 `DataUpload` 不会 skip；依赖后端 resume“只补缺失”。联调时确认 beta/prod resume 行为。  
2. **调用方兼容**：返回值从 session 摘要变为 `skipped` 结构，脚本/pipeline 解析需兼容。  
3. **`incomplete` 粘性**：一旦失败并标 incomplete，同对象上只能走 `resume_upload`；若用户误以为“再调 upload_episode 即可”，会卡住——错误文案与文档需在 FAQ/对内说明里强调。  
4. **部分成功边界**：客户端标 `completed` 只表示本 SDK 本轮文件+manifest 上传流程走完；若后端后续 worker 校验失败，本地仍可能认为 completed。跨系统一致性靠后端状态查询，不在本提交范围内，但联调时建议查 `wait_for_upload` / Admin 状态。  
5. **路径归属规则**：`relative_path == "{key}.mcap"` 或 `startswith("{key}/")`；异常命名（前缀碰撞如 `episode_1` vs `episode_10`）需确认不会误删 URL——`episode_10` 不会匹配 `episode_1/` 前缀，但 `episode_1.mcap` 精确匹配；建议用真实命名样例回归一次。

---

## 7. 结论

`e3fe640` 在客户端为每个 `(upload_id, episode)` 增加了 **completed / incomplete / active** 状态，并改进了 **session 级 URL 缓存与并发 resume 锁**：

- 成功重复调用 → 本地 skip；  
- 失败 → 强制 `resume_upload`；  
- 多集顺序上传 → 按集剔除 URL、保留 session；  
- 并发 refresh → 单飞 resume。

QA 重点验证 **P0 四条路径（skip / 强制 resume / 顺序多集 / upload_session 后再单集）**，再用并发、过期、跨进程做 P1 补强即可覆盖本提交意图。

---

## 8. TC-10 核对：错误提示与 README 是否一致

> 核对日期：2026-08-07  
> 对照：`sdk-vla-foundry` 分支 `codex/fix-episode-upload-cache`，`README.md` vs `prismax/upload.py` / `prismax/data_upload.py`

### 8.1 一致的部分

| README 说法 | 代码行为 |
| --- | --- |
| 同进程、同 `DataUpload`，完成后再次 `upload_episode` 会 **skipped** | 返回 `skipped=True, reason=already_completed` |
| 失败后用 **`resume_upload()`** 补传缺失文件 | `incomplete` 时抛错，并提示 `Resume with prismax.resume_upload(...)`；上传失败的 `PrismaxApiError` 同样带该提示 |
| 未声明 episode 不能追加 | `Episode 'x' is not declared in this DataUpload.` |
| 上传失败后错误里带 resume 指引（README Errors 节） | `upload_episode` / `upload_session` 失败文案含 `Resume with prismax.resume_upload(...)` |

README 原文（行为描述）：

> Within the same process and `DataUpload` object, a completed episode is skipped if `upload_episode()` is called for it again. If an earlier attempt failed, use `resume_upload()` so the backend can identify and upload only missing files.

相关代码文案示例：

```text
# completed 后再次调用：返回（非异常）
{"upload_id": ..., "episode_key": "...", "skipped": True, "reason": "already_completed"}

# incomplete 后再调 upload_episode
Episode 'episode_1' was already attempted but did not complete. Resume with prismax.resume_upload(<id>, data_upload).

# 上传过程中失败
Upload <id> failed while uploading episode 'episode_1'. Resume with prismax.resume_upload(<id>, data_upload). Original error: ...

# 同集并发
This episode is already being uploaded by this process: episode_1.

# 未声明 episode
Episode 'episode_3' is not declared in this DataUpload.
```

### 8.2 不一致 / README 未写清的部分

1. **Skip 返回值**  
   README 只说 “skipped”，**没写**返回结构 `{skipped, reason: already_completed}`。调用方若只看 README，不知道第二次返回形态变了。

2. **失败后再调 `upload_episode` 会被直接拒绝**  
   README 只说 “用 resume_upload”，**没写**再调 `upload_episode` 会抛上述 `was already attempted but did not complete`。行为符合文档意图，但错误文案本身 README 未收录。

3. **并发同集互斥**  
   README 写 “Episode uploads may run concurrently”（指不同集可并发），代码对**同一** episode 会报 `already being uploaded`。README **未说明**同集不可并发。

4. **参数名小差异**  
   错误文案里是 `prismax.resume_upload({id}, data_upload)`，README 示例用的是变量名 `data`。语义一致，复制粘贴时变量名可能对不上。

### 8.3 TC-10 判定结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 行为一致性 | **Pass** | 完成 skip、失败走 resume、失败错误带 resume 指引 —— 与 README 描述一致 |
| 文档完整度 | **Partial** | skip 返回结构、incomplete 拒绝直重试的具体文案、同集并发错误 —— README 未覆盖 |

若要把 TC-10 标严格 Pass，建议补 README：

- skip 返回示例（含 `skipped` / `reason`）  
- 失败后不可再调 `upload_episode`，须 `resume_upload`  
- （可选）同进程同 episode 不可并发上传的说明
