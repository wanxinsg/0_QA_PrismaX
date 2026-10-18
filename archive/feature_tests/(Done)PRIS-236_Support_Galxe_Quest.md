# PRIS-236 Galxe Quest 集成（更新版）Commit 分析与 QA 测试策略

<p style="color: green;"><strong>今日修改说明：</strong>以下标记为绿色文字的段落/标题为今天新增或重写的内容。</p>

## 分析范围

本次文档基于当前后端 `origin/main` 最近 3 个 Galxe 相关提交进行重整：

- `ae6c89a` - `added galxe`
- `ffbbc9a` - `fixing issue`
- `843eb58` - `chagned to rest api`

---

<h2 style="color: green;">一句话主线</h2>

<p style="color: green;">这组改动体现了 Galxe 集成方案从 <strong>“后端主动调用 Galxe GraphQL 追加 credential”</strong> 演进为 <strong>“后端提供 REST 校验接口给 Galxe 查询注册资格”</strong>。当前主流程以 REST 方案为准。</p>

---

## 版本演进（按 commit）

## 1) `ae6c89a` - `added galxe`

**目标**：接入 `source=galxe` 来源追踪，并在登录后触发 Galxe GraphQL 同步。

**核心变更：**

- `app.py` 的 `get_users()` 新增 `source` 白名单（仅 `galxe`）。
- `users` 表新增 `acquisition_source` 字段（SQL migration）。
- 新钱包注册或老钱包补标来源后，触发 `append_wallet_to_credential()`。
- 新增 `galxe_credential.py`，封装 GraphQL `credentialItems(APPEND)` 调用。
- 新增 `test_galxe_credential.py` 单测。

**当时链路：**

`?source=galxe` -> `GET /api/get-users` -> 落库 `acquisition_source` -> 调 Galxe GraphQL -> quest 可校验。

## 2) `ffbbc9a` - `fixing issue`

**目标**：增强 GraphQL 调用失败场景可观测性。

**核心变更：**

- `galxe_credential.py` 不再直接 `raise_for_status()`。
- 对 HTTP 非 2xx 显式记录 `status_code + response body`。
- 区分网络异常与 JSON 解析异常日志。
- 补充对应单元测试（验证错误体被记录）。

**价值：**

提高排障效率，避免 Galxe 失败只看到模糊异常。

<h2 style="color: green;">3) <code>843eb58</code> - <code>chagned to rest api</code>（当前生效方案）</h2>

<p style="color: green;"><strong>目标</strong>：改为 Galxe 调用 Prismax REST 接口校验注册，不再由 Prismax 主动 push GraphQL。</p>

<p style="color: green;"><strong>核心变更：</strong></p>

<p style="color: green;">- 新增接口：<code>GET /api/galxe/verify-registration</code>（含 <code>OPTIONS</code>）。</p>
<p style="color: green;">- 新增 <code>galxe_rest_credential.py</code>，封装地址标准化、API Key 鉴权（<code>X-Galxe-Api-Key</code> 或 <code>Authorization: Bearer</code>）、统一响应结构（含 <code>eligible</code> 数字位）。</p>
<p style="color: green;">- 删除 <code>galxe_credential.py</code> 及其测试，新增 <code>test_galxe_rest_credential.py</code>。</p>
<p style="color: green;">- <code>get_users()</code> 中删除“触发 Galxe GraphQL 同步”的逻辑。</p>
<p style="color: green;">- 配置改为读取 <code>GALXE_REST_API_KEY</code>（环境变量或 Secret Manager）。</p>

---

<h2 style="color: green;">当前线上逻辑（以 <code>843eb58</code> 为准）</h2>

## 1) 登录链路（`/api/get-users`）

- 仍保留 `source` 白名单逻辑：仅 `source=galxe` 才会写入 `acquisition_source`。
- 登录和注册主流程不再触发 Galxe GraphQL 外部调用。
- 即：`get_users` 负责用户登录/注册与来源落库，不再负责 quest 资格同步。

<h3 style="color: green;">2) Galxe 校验链路（新增 REST 接口）</h3>

<p style="color: green;">接口：<code>GET /api/galxe/verify-registration</code></p>

入参地址支持 3 个 key（取第一个非空）：

- `address`
- `wallet_address`
- `solana_address`

鉴权：

- Header `X-Galxe-Api-Key: <key>` 或
- Header `Authorization: Bearer <key>`

后端判定逻辑：

```sql
SELECT userid
FROM users
WHERE solana_receive_address = :address
  AND acquisition_source = 'galxe'
LIMIT 1;
```

返回语义：

- 查到：`registered=true`, `is_ok=true`, `eligible=1`
- 查不到：`registered=false`, `is_ok=false`, `eligible=0`

---

<h2 style="color: green;"><code>/api/galxe/verify-registration</code> 响应契约</h2>

## 成功 200（registered）

```json
{
  "success": true,
  "address": "7xZ...",
  "registered": true,
  "is_ok": true,
  "eligible": 1
}
```

## 成功 200（not registered）

```json
{
  "success": true,
  "address": "7xZ...",
  "registered": false,
  "is_ok": false,
  "eligible": 0
}
```

## 401 Unauthorized（API key 不通过）

```json
{
  "success": false,
  "registered": false,
  "is_ok": false,
  "eligible": 0,
  "msg": "Unauthorized"
}
```

## 400 Missing address

```json
{
  "success": false,
  "registered": false,
  "is_ok": false,
  "eligible": 0,
  "msg": "Missing address"
}
```

## 503 配置缺失

```json
{
  "success": false,
  "registered": false,
  "is_ok": false,
  "eligible": 0,
  "msg": "Galxe REST API key is not configured"
}
```

<h3 style="color: green;">curl 示例（REST verify-registration）</h3>

使用 `X-Galxe-Api-Key`：

```bash
curl -X GET "https://user.prismaxserver.com/api/galxe/verify-registration?address=7xZMMKjZtonV5QEBTcUZ23R3Ut7zyn4tgyfhPCVQbeLL" \
  -H "X-Galxe-Api-Key: YOUR_GALXE_REST_API_KEY"
```

使用 `Authorization: Bearer`：

```bash
curl -X GET "https://user.prismaxserver.com/api/galxe/verify-registration?address=7xZMMKjZtonV5QEBTcUZ23R3Ut7zyn4tgyfhPCVQbeLL" \
  -H "Authorization: Bearer YOUR_GALXE_REST_API_KEY"
```

---

<h2 style="color: green;">端到端新时序（当前）</h2>

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant FE as app-prismax-rp
    participant BE as app-prismax-rp-backend
    participant DB as PostgreSQL
    participant GX as Galxe

    U->>FE: 访问 ?source=galxe 并登录
    FE->>BE: GET /api/get-users?...&source=galxe
    BE->>DB: 写入/保留 users.acquisition_source
    BE-->>FE: 200 登录成功

    GX->>BE: GET /api/galxe/verify-registration?address=...
    Note over GX,BE: 携带 X-Galxe-Api-Key 或 Bearer
    BE->>DB: 查询 solana_receive_address + acquisition_source='galxe'
    BE-->>GX: 200 + eligible(1/0)
```

---

<h2 style="color: green;">QA 测试策略（更新版）</h2>

## 1) 测试目标

- 验证来源采集仍正确：`source=galxe` 仅白名单写库。
- 验证新 REST 校验接口的鉴权、参数和返回契约。
- 验证从旧 GraphQL 方案切换到 REST 后无登录回归。
- 验证异常路径（无 key、错误 key、缺地址、DB 异常）可预期。

## 2) 测试范围分层

- 前端集成：`source=galxe` 的存储与透传是否仍存在。
- 登录 API：`/api/get-users` 对 `acquisition_source` 落库是否正确。
- Galxe REST API：`/api/galxe/verify-registration` 契约正确性。
- 回归测试：无 `source` 登录、email+wallet 绑定、reCAPTCHA 主流程。

---

<h2 style="color: green;">E2E 关键用例（当前版本）</h2>

| Priority | Case ID | 测试场景 | 前置条件 | 测试步骤 | 预期结果 |
|---|---|---|---|---|---|
| P0 | GX-RST-01 | 已注册 Galxe 用户返回 eligible=1 | 钱包 A 在 DB 中，`acquisition_source='galxe'` | 调 `GET /api/galxe/verify-registration?address=A` + 正确 API key | 200；`registered=true`；`eligible=1` |
| P0 | GX-RST-02 | 非 Galxe 来源用户返回 eligible=0 | 钱包 B 在 DB 中但 `acquisition_source` 非 `galxe` 或为空 | 同上调用地址 B | 200；`registered=false`；`eligible=0` |
| P0 | GX-RST-03 | 未注册钱包返回 eligible=0 | 钱包 C 不存在 | 同上调用地址 C | 200；`registered=false`；`eligible=0` |
| P0 | GX-RST-04 | 鉴权失败 | 有测试地址 | 不带 key 或带错误 key 调用 | 401；`msg=Unauthorized` |
| P0 | GX-RST-05 | 缺少地址参数 | API key 正确 | 调 `/api/galxe/verify-registration` 不带地址 | 400；`msg=Missing address` |
| P1 | GX-RST-06 | API key 未配置 | 环境无 `GALXE_REST_API_KEY` | 正常调用 | 503；配置缺失提示 |
| P1 | GX-RST-07 | Bearer 鉴权兼容 | API key 正确 | `Authorization: Bearer <key>` 调用 | 鉴权通过，行为与 X-Galxe-Api-Key 一致 |
| P1 | GX-RST-08 | CORS/OPTIONS | 无 | 发 OPTIONS 预检 | 204；含 CORS 允许头 |
| P1 | GX-RST-09 | 地址字段兼容 | 有测试地址 | 分别用 `address`、`wallet_address`、`solana_address` 调用 | 三种参数均可被识别 |

---

## `/api/get-users` 相关回归用例（保留）

| Priority | Case ID | 场景 | 步骤 | 预期结果 |
|---|---|---|---|---|
| P0 | GX-REG-01 | `source=galxe` 新钱包登录 | 前端带参进入后登录 | `users.acquisition_source='galxe'` |
| P0 | GX-REG-02 | 非法 source 被忽略 | `source=twitter` 或 `source=GALXE` 登录 | 不写入 `acquisition_source` |
| P1 | GX-REG-03 | 与 referral 并存 | `?source=galxe&ref=ABC123` 登录 | `acquisition_source` 与 referral 均正确写入 |
| P1 | GX-REG-04 | 无 source 正常回归 | 正常登录 | 行为与改动前一致 |

---

<h2 style="color: green;">单元测试回归清单（更新）</h2>

当前应重点回归：

- `test_galxe_rest_credential.py`
  - 地址标准化
  - API key 鉴权（header/bearer）
  - 响应结构 `eligible` 数字位

执行命令（backend 目录）：

```bash
cd app_prismax_user_management
python -m unittest test_galxe_rest_credential.py -v
```

---

<h2 style="color: green;">环境检查清单（测试前）</h2>

- [ ] DB 已执行 `20260615_add_users_acquisition_source.sql`
- [ ] 环境已配置 `GALXE_REST_API_KEY`（env 或 Secret Manager）
- [ ] Galxe 侧已配置调用 `https://user.prismaxserver.com/api/galxe/verify-registration`
- [ ] Galxe 请求头已带 `X-Galxe-Api-Key` 或 Bearer
- [ ] 测试数据包含三类地址：galxe 来源、非 galxe 来源、未注册

---

<h2 style="color: green;">结论</h2>

<p style="color: green;">PRIS-236 当前已从“后端主动 GraphQL 同步”切换为“Galxe 主动调用 REST 校验”。<br>因此 QA 重点应从“GraphQL 成功与否”转为“REST 契约稳定性 + 鉴权正确性 + DB 来源数据准确性”。在此基础上保留 <code>/api/get-users</code> 的来源落库回归，才能确保 quest 识别链路闭环。</p>

