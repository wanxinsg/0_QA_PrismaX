# 管理员浏览器下载：Commit 逻辑分析与测试用例

> 分析日期：2026-10-14（UTC+8）  
> 范围：`app-prismax-rp`、`app-prismax-rp-backend`  
> 营销站 `prismax-marketing-rp` 没有这条功能。  
> 两条线都在各自 `testing` 上，作者是 lanmanc。

管理员在 Robotic Data 的 Uploads 里勾选最多 30 条已就绪 episode，向固定收件人要一次性验证码，再用这个浏览器把签名链接逐个存下来。验证码请求打用户邮件服务，真正签名和历史打 data pipeline。

| 仓库 | Commit | 时间（`-0400` / 北京时间） | Message |
| --- | --- | --- | --- |
| 前端 | `e3ddec51fa33a73b1eec2f862d2494d898b3fc8d` | 10-13 16:23 / 10-14 04:23 | Add admin browser downloads with thirty episode selection and history |
| 后端 | `1e362e2293bf242e91e47385a9be172de339365f` | 10-13 16:23 / 10-14 04:23 | Enable secure admin browser downloads and show all upload tasks |
| 前端 | `5ae2b109a25257acefef99cabe816a3ffeb0506d` | 10-13 17:33 / 10-14 05:33 | Add email verification dialog before administrator downloads |
| 后端 | `267db7638955436f1aae996caeb44e95e6a3b487` | 10-13 17:33 / 10-14 05:33 | Require one-time email verification for admin browser downloads |
| 前端 | `527aff178fad0099da52ee0a2cddeead78371842` | 10-13 17:56 / 10-14 05:56 | Fix admin download verification requests blocked by API domain challenges |
| 后端 | `66eac121f7a8d5da45253e624f0c1b953c434581` | 10-13 18:18 / 10-14 06:18 | Add authenticated admin code delivery to the existing user email service |
| 后端 | `436964db5aa871b4ee6536772c55b061b421bf85` | 10-13 18:18 / 10-14 06:18 | Delegate admin code delivery to the existing user email service |
| 后端 | `66deac1d2999b2a97d6b40099fcb6ae1389a2de3` | 10-13 18:29 / 10-14 06:29 | Send admin download codes directly through existing user mail service |
| 前端 | `03448c2883e236a1a80ffcbd39071c556d22dd2d` | 10-13 18:30 / 10-14 06:30 | Request admin download codes from existing user mail service |
| 前端 | `c4c1363bd6ab4e5219610afe8a30b0d961f59ab4` | 10-13 18:56 / 10-14 06:56 | Reuse selected episodes sidebar for admin downloads and add Chris |
| 后端 | `9a2a2f55f475812b5decf86a9259330972314eeb` | 10-13 18:55 / 10-14 06:55 | Allow Chris as a fixed admin download verification recipient |

---

## 1. 业务目标

普通会员下载仍走原来的配额和可见任务。这条链路只给管理员：

- Uploads 列出全部任务的上传，不再按环境可见性丢掉任务。
- 成功 episode 可以勾进右侧已选列表，最多 30 条。失败视图不能勾。
- 下载前必须向 Jason、Bayley、Chris 三人中的一个发 8 位验证码。收件人列表是写死的，不能改成任意邮箱。
- 验证码 5 分钟内、一次性、只对这一组 episode、这一次登录、这一个环境有效。
- 签名链接 30 分钟。浏览器按文件逐个下载。历史只说明链接有没有备好，不说明文件一定落盘。

---

## 2. 数据流

```text
Uploads 勾选 1–30 个 DERIVED_READY episode
        │
        ▼
POST {用户服务}/data/admin/downloads/verification
body 只能有 selected_episode_ids + recipient
        │  admin JWT + admin_whitelist 行锁
        │  全部 episode 必须 DERIVED_READY
        │  频率限制通过后才生成 8 位码
        ▼
data_admin_download_challenges（status=SENDING，只存 HMAC，不存明文）
        │
        ▼
现有用户邮件服务发给固定收件人
        │  失败 → SEND_FAILED，摘要清掉，503
        │  成功 → SENT
        ▼
管理员把 8 位码填回对话框
        │
        ▼
POST {data pipeline}/data/admin/downloads/ui
body 只能有 selected_episode_ids + challenge_id + verification_code
        │  同一事务里核销验证码，并插入 data_admin_downloads
        │  核销之后才签 GCS URL（30 分钟）
        ▼
浏览器按 files[] 顺序逐个下载
        │
        ▼
GET {data pipeline}/data/admin/downloads/history
只返回当前 admin_id + wallet 的记录
```

两个域名不能混用：

| 环境 | 要验证码 | 签名下载和历史 |
| --- | --- | --- |
| 本地 | `http://127.0.0.1:8080` | `http://127.0.0.1:8082` |
| Beta 页面 `beta-app.prismax.ai` | `https://beta-user.prismaxserver.com` | `https://app-prismax-data-pipeline-beta-1053158761087.us-west1.run.app` |
| 生产页面 `app.prismax.ai` | `https://user.prismaxserver.com` | `https://app-prismax-data-pipeline-1053158761087.us-west1.run.app` |

生产下载不走 `data.prismaxserver.com`。验证码是带 Authorization 的跨域请求，打在会出 Cloudflare challenge 的域名上时预检过不去。Data pipeline 上残留的 `POST /data/admin/downloads/verification` 固定返回 `410`，文案 `Please refresh the page before requesting a code.`

邮件服务把部署名映射成 pipeline 的环境名，验证码才能在对的环境里核销：

| 发信服务 `K_SERVICE` | challenge 上记下的 environment |
| --- | --- |
| `app-prismax-backend-beta` | `app-prismax-data-pipeline-beta` |
| `app-prismax-backend` | `app-prismax-data-pipeline` |
| 其他非空值 | 直接拒绝，`Unknown mail deployment` |
| 未设置 | `PRISMAX_ENV`，再没有就是 `local` |

核销时 pipeline 用自己的 `K_SERVICE`（或 `PRISMAX_ENV` / `local`）去对这列。Beta 的码不能拿到生产去用。

---

## 3. 后端

测之前按这个顺序跑 SQL，后一个会改前一个的收件人约束：

1. `20261013_admin_browser_downloads.sql`：`data_admin_downloads`
2. `20261013_admin_download_verification.sql`：`data_admin_download_challenges`，当时只允许 `jason`、`bayley`
3. `20261013_admin_download_mail_dispatch.sql`：发信时间和发信服务两列
4. `20261013_admin_download_chris_recipient.sql`：收件人约束改成 `jason`、`bayley`、`chris`

下载审计行在管理员被移出 `admin_whitelist` 之后仍保留。

### 3.1 固定收件人

| recipient | 界面和历史上的掩码 | 实际收件地址 |
| --- | --- | --- |
| `jason` | `Ja****` | `jason@prismax.ai` |
| `bayley` | `Ba***` | `Bayley@prismax.ai` |
| `chris` | `Ch***` | `chris@prismax.ai` |

邮件主题是 `PrismaX admin download verification code`。正文有验证码、管理员编号、钱包、环境、episode 列表，并写明 5 分钟、一次性、只对这一组 episode。`sensitive=True`，明文码不进普通日志，也不出现在接口响应里。

响应只有 `challenge_id`、`recipient_label`、`expires_at`、`resend_after_seconds`（60）。

### 3.2 要验证码

`POST /data/admin/downloads/verification`，挂在用户服务上。

| 条件 | 结果 |
| --- | --- |
| 没有或无效 JWT | `401` `invalid token`，不查库、不发信 |
| role 不是 admin，或不在 `admin_whitelist` | `403` `admin access required` |
| body 除了 `selected_episode_ids` 和 `recipient` 还有别的字段 | `400` `Provide selected_episode_ids and recipient only.` |
| 不是 1–30 个正整数，或 recipient 不在上表 | `400` `Select 1 to 30 episodes and a listed recipient.` |
| 有 episode 不是 `DERIVED_READY`，或根本不存在 | `400` `One or more selected episodes are not ready for download.`，不发信 |
| 发信失败 | `503` `Could not send the code. Please wait a minute and try again.`；行变成 `SEND_FAILED`，摘要清空 |
| 发信过程中这条 challenge 已被新请求替换 | `409` `This code request was replaced. Request a new code.` |

ID 会先去重再排序后入库。`true`、`1.5`、`0`、负数、字符串、`2^63` 都算非法。布尔值不会被当成整数。

同一管理员、同一环境里，新的 `SENDING` / `SENT` 会把旧码标成 `SUPERSEDED` 并清掉摘要。发信还没完成时（仍是 `SENDING`），这组码不能拿去下载。

频率限制按 `data_admin_download_challenges` 最近一小时统计，失败的发信也算。所有管理员、所有环境共用收件人额度：

| 限制 | 阈值 | 超过时 |
| --- | --- | --- |
| 该管理员任意新请求 | 60 秒内已有一条 | `429` `Too many code requests. Please try again later.` |
| 该管理员每小时 | 10 条 | 同上 |
| 同一收件人每分钟 | 5 条，跨管理员 | 同上 |
| 同一收件人每小时 | 30 条，跨管理员 | 同上 |

并发的两次发送只会有一次真正发信，另一次 `429`。换收件人不能绕过这 60 秒。

### 3.3 核销并签名

`POST /data/admin/downloads/ui`，挂在 data pipeline 上。body 必须正好是三个字段：`selected_episode_ids`、`challenge_id`、`verification_code`。多一个字段，包括旧客户端只传 episode，都是 `400` `A download verification code is required.`，不会签名。

验证码必须是 8 位数字，`challenge_id` 必须是小写 UUID。核销条件同时成立才通过：

- 同一 `admin_id`、同一钱包、同一 JWT `jti` 的会话哈希、同一 environment
- 状态是 `SENT`，未过期，尝试次数小于 5
- HMAC 对得上，且 episode 集合和申请时完全一致

对不上时统一 `403`：`Invalid or expired verification code. Request a new code if needed.` 错误尝试加 1。第 5 次把状态改成 `LOCKED` 并清掉摘要，之后正确的码也不能用。成功则 `CONSUMED`，摘要清掉，不能重放。两个并发请求只会有一个 `200`。

核销和插入 `data_admin_downloads` 在同一个事务里，提交之后才去签链接。所以准备文件失败时码已经作废，必须重新要码。失败行的 `status=FAILED`，`error_message` 末尾带 `Please request a new code to retry.`

签名只认库里的路径，不接受客户端传来的 path。每条都必须是 `DERIVED_READY`。任务不可见也可以下，查询不加 `is_visible`。原始目录必须落在 `raw/<upload_id>/` 下面、以 `/` 结尾，且不能是整个 upload 前缀，也不能含 `..`。空目录或跨 upload 的路径在列对象之前就拒绝。链接有效期 30 分钟（1800 秒）。响应 `Cache-Control: no-store`。不写 `data_user_library`。

这条接口另外还有每分钟 5 次下载审计。按该管理员 `data_admin_downloads.created_at` 计数，准备失败的行也算。超过则 `429`，`Retry-After: 60`，文案 `Too many download requests. Try again in a minute.`，并且还没签名。事务里会再锁一次白名单，中途被取消资格的管理员是 `403`。

存储异常对客户端只返回 `Failed to prepare administrator download. Please request a new code to retry.`，HTTP `500`。内部异常文本不进响应，也不写进 `error_message`。

### 3.4 历史

`GET /data/admin/downloads/history`。查询参数里的 `admin_id` 被忽略，只用 JWT 里的管理员和钱包。普通用户 `403`。`before_id` 非法（含负数）是 `400` `Invalid history cursor.`

每页最多 50 条，按 `download_id` 倒序。多于 50 时 `pagination.next_before_id` 是本页最后一条的 id。字段含 `verification_recipient`、`status`、`file_count`、`total_bytes`、`error_message`、`selected_episode_ids`、`created_at`、`expires_at`。同样 `Cache-Control: no-store`。

### 3.5 上传列表不再按可见性过滤

`GET /data/admin/downloadable-upload-groups` 不再读任务可见性列，也不再因为 `PRISMAX_ENV` 或 `include_test_uploads=false` 丢掉任务。管理员能看到每个有目标状态 episode 的上传。

显式筛选还在：`task_ids` 去重排序后按任务过滤，`job_id` 按 job 过滤。`failed_only=true` 时 episode 状态用 `DERIVED_VALIDATION_FAILED`，否则用 `DERIVED_READY`。非法 `task_ids` 在查询之前 `400`。

---

## 4. 管理端页面

入口在 Admin Robotic Data 的 Uploads。成功数据的卡片上有 `Select for download`。Failed only 视图不渲染这个勾选框。

右侧栏就是原来的 Selected episodes：

| 区域 | 行为 |
| --- | --- |
| 已选芯片 | `Ep <id> ×`，点一下从选择里去掉 |
| Clear selection | 清空。对话框打开或正在下载时禁用 |
| Episodes | `n / 30` |
| Video files | 每条都有数字 `video_count` 时求和，否则 `—` |
| MCAP files | 等于已选条数，不是服务端真实文件数 |
| Browser | 说明最多 30 条、要邮箱验证、链接 30 分钟。按钮 `Browser Download` |
| History | `My download history` |

第 31 条的勾选框禁用。已选中的仍可取消。对话框打开或下载进行中，勾选框也禁用。换管理员 token 会清空选择。

`Browser Download` 先只打开对话框，此时还不发请求。默认收件人是 `Ja****`。三个单选是 `Ja****`、`Ba***`、`Ch***`。

| 操作 | 行为 |
| --- | --- |
| Send code | `POST` 用户服务 `/verification`，body 是当前已选 id 和 `jason` / `bayley` / `chris` |
| 发送成功 | `Code sent to <掩码>. Valid for 5 minutes.` 验证码框可用 |
| 60 秒内 | 按钮变成 `Resend in Ns` 并禁用。换收件人会清掉已填验证码和当前 challenge，但冷却还在 |
| 满 5 分钟 | 输入框和 Verify 禁用，文案 `Code expired. Please request a new code.`，Resend 可用 |
| 验证码框 | 只留数字，最多 8 位。不满 8 位不能提交 |
| Verify and download | `POST` pipeline `/ui`。成功后关对话框，按返回的 `files` 顺序下载 |
| 错误码 | 对话框留着，alert 显示接口 `msg`，不下载文件 |
| Cancel 或 Escape | 关对话框，不发请求，选择解锁。请求进行中 Escape 无效 |
| 某个文件失败 | 停在该文件，不再下后面的；alert 是浏览器侧的错误 |
| 链接过期 | `Download links expired. Select the remaining episodes and download again.` |

下载过程的状态文案是 `Downloading i/n: <文件名>`，全部完成后是 `<n> files sent to your browser. Check your browser downloads to confirm they were saved.` 页面提示 `Allow multiple downloads in your browser.`

历史状态文案：`LINKS_READY` → `Links generated`，`FAILED` → `Preparation failed`，`PENDING` → `Preparation pending`。有收件人时显示 `Email verified: <掩码>`。超过 50 条出现 `Older records`，用 `before_id` 接着拉。说明文字：`Records show link preparation, not confirmation that files were saved.`

这些 `/data/admin/downloads/` 响应都带 `Cache-Control: no-store`。

---

## 5. 单测已经锁住的行为

后端 `test_admin_browser_downloads.py`：无 token `401`；普通用户带 `admin: true` 也不能签名；过期 token、已撤销管理员、事务中途被撤销都在签名前拒绝；没有验证码的旧请求 `400`；错码不插入下载行；正好 30 条可以，响应不落库签名 URL，也不写 `data_user_library`；31 条、空、布尔、小数、0、负数、过大整数、字符串都在审计和签名之前 `400`；多传 `path`、`admin_id`、`enforce_task_visibility`、`selected_upload_ids` 一律 `400`；每分钟第 5 次之后 `429` 且带 `Retry-After: 60`；episode 不就绪写成 `FAILED`；存储异常的原文不出现在响应里；历史忽略客户端传来的 `admin_id`，每页 50；隐藏任务仍要求 `DERIVED_READY`，目录为空或跨 upload 时不列存储。

后端 `test_admin_download_verification.py`（需要本地一次性 Postgres）：三个收件人都能下 30 条；码不重放；并发只有一次签名；5 次错误后 `LOCKED`；过期、换会话、换钱包、换 episode、换环境都是 `403`，原会话仍可用；重发使旧码失效；发信失败后摘要为空且占用冷却；换收件人绕不过 60 秒；每小时 10 次；同一收件人 5 个管理员之后第 6 个 `429`；并发发送只发一封；撤销后不能再发也不能再核销；任意邮箱和普通用户不能发；发信完成前不能核销；准备文件失败后码已 `CONSUMED`。

后端 `test_admin_download_email.py`：beta / 生产的环境名映射；未知 `K_SERVICE` 抛错；两边的 HMAC 和会话哈希一致；非 admin 不碰数据库。

后端 `test_data_membership_downloads.py`：`test_admin_upload_groups_include_all_tasks_in_both_environments` 确认生产、beta、以及 `include_test_uploads=false` 都不加可见性条件。

前端 `AdminBrowserDownloads.test.js`、`RoboticDataAdmin.downloads.test.js`、`config.adminDownloads.test.js`：30 条上限、失败视图不可选、验证码打用户服务、下载打 pipeline 直连、错码不拉文件、取消不发请求、过期后不能提交、Chris 作为固定收件人、历史分页，以及三个环境的下载基址。

---

## 6. 已知实现口径

执行下面的用例时按这些判定，不要当成缺陷：

1. 验证码请求和下载不是同一个 host。生产下载基址是 data pipeline 的 Cloud Run，不是 `data.prismaxserver.com`。
2. 接口响应、历史、对话框都不出现完整邮箱，只出现 `Ja****` / `Ba***` / `Ch***`。Bayley 的真实地址是 `Bayley@prismax.ai`，B 大写。
3. 60 秒冷却按管理员计，不按收件人计。换人重发立刻会 `429`。失败的发信同样占冷却和每小时 10 次。
4. 收件人的每分钟 5 次、每小时 30 次是所有管理员加在一起的。Beta 上如果别人刚用过同一个收件人，自己会先碰到 `429`。
5. 准备文件失败或存储失败之后，这组码不能再用。下载审计行已经写成 `FAILED`，并计入每分钟 5 次。
6. 历史里的 `Links generated` 只表示签名完成。浏览器中途关掉、拦截多文件下载，历史不会变成失败。
7. 侧栏的 MCAP 数字等于 episode 条数。真正下下来的文件还可能有视频和 URDF，以接口 `files[]` 为准。
8. Video files 在某条没有数字 `video_count` 时显示 `—`。
9. 客户端多传的 `admin_id` 不能用来看别人的历史，也不能指定别的管理员去签名。
10. Failed only 没有勾选框。不可见任务的成功 episode 可以出现，也可以下载。
11. 对话框打开期间不能改选择。要换 episode 必须先关掉对话框，等冷却结束后重新发码。旧码会失效。
12. 验证码和这一次登录的 `jti` 绑在一起。刷新如果换成新 token，旧码不能用。

---

## 7. 测试数据与环境

- 目标库已按第 3 节的顺序执行 4 个 SQL。只跑到第二个脚本时，选 Chris 会被数据库约束拒绝。
- 一个仍在 `admin_whitelist` 里的管理员账号。另备一个普通用户 token，以及一个已从白名单删除的旧管理员 token。
- 至少 31 条 `DERIVED_READY`、原始文件路径合法的 episode，其中最好有一条属于当前环境里「不可见」的任务。
- 一条非 `DERIVED_READY` 的 episode，用来确认发信前就拒绝。
- 能看 Jason、Bayley、Chris 三个邮箱。不要把验证码转发到这三个人以外的地址。
- 浏览器：桌面 Chrome，允许多个文件下载。DevTools 里分别看用户服务和 pipeline 直连。
- 频率用例会把收件人额度打满。放到测试窗口的后段，或换一个这一小时没被别人用过的收件人。

---

## 8. 测试用例

优先级：P0 必测 / P1 重要 / P2 补充。

| 分类 | ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 选择和入口 | ADM-DL-001 | P0 | 成功 episode 才能勾选 | 管理员打开 Uploads，列表里有成功数据 | 展开一条上传，勾选若干 `Select for download` | 右侧出现 `Ep <id> ×`；Episodes 变成 `n / 30`；未点 Browser Download 时没有 verification 或 ui 请求 |
| 选择和入口 | ADM-DL-002 | P0 | 第 31 条不能选 | 同一列表至少 31 条成功 episode | 勾满 30 条，再点第 31 条 | 第 31 个勾选框禁用；计数停在 `30/30`；已选的 30 条仍可取消。取消一条后第 31 条恢复可点 |
| 选择和入口 | ADM-DL-003 | P0 | 失败视图不能下载 | 同一页能切到 Failed only | 点 Failed only | 卡片上没有 `Select for download`；`Browser Download` 禁用 |
| 选择和入口 | ADM-DL-004 | P1 | 不可见任务仍出现 | 有一条任务在当前环境 `is_visible` 为假，但有 `DERIVED_READY` episode | 打开 Uploads，不传 `task_ids` | 该上传出现在列表里。抓包 `GET /data/admin/downloadable-upload-groups`，查询没有按可见性过滤。再带 `include_test_uploads=false` 结果相同 |
| 选择和入口 | ADM-DL-005 | P1 | 显式筛选仍生效 | 知道一个 task_id 和一个 job_id | 分别带 `task_ids`、`job_id` 请求上传列表 | 只返回对应任务或 job。`task_ids=bad` 返回 `400`，不查库 |
| 选择和入口 | ADM-DL-006 | P2 | 侧栏计数 | 每条 episode 都有 `video_count` | 勾选若干条 | Video files 是这些 `video_count` 之和；MCAP files 等于条数。去掉 `video_count` 的数据时 Video files 为 `—` |
| 选择和入口 | ADM-DL-007 | P1 | 换账号清空选择 | 已勾选若干条 | 换成另一个管理员 token 重新进入 | 选择清空，下载状态复位 |
| 验证码 | ADM-DL-008 | P0 | 先发码再下载 | 已选 1 条就绪 episode | 点 Browser Download | 只出现对话框，默认 `Ja****` 选中，此时没有网络请求。Clear selection 和勾选框禁用 |
| 验证码 | ADM-DL-009 | P0 | 码发到固定邮箱且响应不含明文 | 三个收件人各做一次，每次间隔超过 60 秒 | 选中一个人，点 Send code，看邮箱和 Network | 请求打用户服务 `/data/admin/downloads/verification`，body 只有 `selected_episode_ids` 和 `jason` / `bayley` / `chris`。响应 `200`，有 `challenge_id`、掩码、`expires_at`、`resend_after_seconds: 60`，没有 8 位数字。邮件进对应邮箱，主题为 `PrismaX admin download verification code` |
| 验证码 | ADM-DL-010 | P0 | 正确码能下载 | 刚收到验证码，选择没变，仍是同一次登录 | 填入 8 位码，点 Verify and download | 请求打 pipeline 直连 `/data/admin/downloads/ui`，不是 `data.prismaxserver.com`。body 正好三个字段。`200` 后浏览器逐个保存 `files[]`。对话框关闭。历史第一条是 `Links generated`，并显示对应掩码 |
| 验证码 | ADM-DL-011 | P0 | 错码不下载 | 已发码 | 输入另一个 8 位数并提交，重复到第 5 次，再用邮件里的正确码 | 每次 `403`，对话框留着，没有文件请求。第 5 次后正确码也是 `403`，文案 `Invalid or expired verification code. Request a new code if needed.` |
| 验证码 | ADM-DL-012 | P0 | 一次性 | 同一组码已经成功下载过 | 不重新发码，再用同一 `challenge_id` 和验证码打 `/ui` | `403`，不再签名 |
| 验证码 | ADM-DL-013 | P0 | 换选择使旧码失效 | 已对一组 episode 发码 | 关掉对话框，改掉选择，等 60 秒后重新 Send code，再用旧码对旧选择打 `/ui` | 旧码 `403`。新码只能下新的那一组 |
| 验证码 | ADM-DL-014 | P1 | 60 秒内不能换人重发 | 刚刚 Send code 成功 | 立刻改选另一个收件人再点发送 | 按钮处于 `Resend in Ns`，或接口 `429` `Too many code requests. Please try again later.` 已填的验证码被清掉 |
| 验证码 | ADM-DL-015 | P1 | 过期 | 发码后把该行 `expires_at` 改成过去，或等满 5 分钟 | 再提交验证码；页面上等满 5 分钟 | 页面上 Verify 禁用，出现 `Code expired. Please request a new code.` 接口直接提交也是 `403`，没有签名 |
| 验证码 | ADM-DL-016 | P1 | 绑定会话和环境 | 用管理员 A 发码 | 用管理员 A 的另一次登录、管理员 B、以及另一个环境的 pipeline 去核销同一组码 | 全部 `403`。原来的登录仍可 `200` |
| 验证码 | ADM-DL-017 | P1 | 未就绪 episode 不发信 | 选择里混入一条不是 `DERIVED_READY` 的 id，或用接口直接提交 | Send code | `400` `One or more selected episodes are not ready for download.` 邮箱没有新邮件 |
| 验证码 | ADM-DL-018 | P1 | 不能指定任意邮箱 | 用接口把 `recipient` 改成别的邮箱，或多加 `subject` | `POST /verification` | `400`，不发信。普通用户 token 是 `403`。没有 token 是 `401` |
| 验证码 | ADM-DL-019 | P2 | 发信失败 | 让邮件服务对这次发送返回失败 | 点 Send code，立刻用邮件里如果出现的码去下载 | 页面 `503`，那条 challenge 为 `SEND_FAILED`，`code_digest` 为空。下载 `403`。60 秒内再发是 `429` |
| 验证码 | ADM-DL-020 | P2 | 每小时 10 次 | 同一管理员，每次把上一条的 `created_at` 拨早 61 秒，或真实等待 | 连续成功发码 10 次后再发第 11 次 | 前 10 次 `200`，第 11 次 `429`，不论换哪个收件人 |
| 下载和历史 | ADM-DL-021 | P0 | 正好 30 条 | 勾满 30 条就绪 episode 并完成验证 | 验证后看下载请求和浏览器下载 | `episode_count` 为 30；`expires_at` 距现在不超过 30 分钟；响应头 `Cache-Control: no-store`；文件按返回顺序下载。个人库 `data_user_library` 不新增这些 episode |
| 下载和历史 | ADM-DL-022 | P0 | 旧请求不能绕过验证码 | 管理员 token 有效 | `POST /ui`，body 只有 `selected_episode_ids` | `400` `A download verification code is required.` 没有签名 URL |
| 下载和历史 | ADM-DL-023 | P0 | 不能传路径或冒充别人 | 已有合法验证码 | body 额外加上 `path`、`admin_id` 或 `selected_upload_ids` | `400`，不签名 |
| 下载和历史 | ADM-DL-024 | P1 | 每分钟 5 次下载 | 同一管理员 1 分钟内已有 5 条 `data_admin_downloads` | 再用新验证码下载 | `429`，`Retry-After: 60`，文案 `Too many download requests. Try again in a minute.` 不签名 |
| 下载和历史 | ADM-DL-025 | P1 | 准备失败要新码 | 能构造一条通过发信校验、但原始路径非法或文件缺失的 episode | 发码并提交 | `400` 或 `500`。选择类错误会带具体原因；存储错误只有 `Failed to prepare administrator download.` 两者都追加 `Please request a new code to retry.` 响应和历史里都没有内部异常或签名 URL。再用同一码提交是 `403`，历史为 `Preparation failed` |
| 下载和历史 | ADM-DL-026 | P0 | 历史只看自己 | 两个管理员各自成功下载过 | 管理员 A 打开 History，并在 URL 上加 `admin_id=<B>` | 只看到 A 的记录。接口参数仍是 A 的 `admin_id` 和钱包。普通用户调历史接口为 `403` |
| 下载和历史 | ADM-DL-027 | P1 | 历史分页和文案 | A 的记录超过 50 条 | 打开 My download history，点 Older records | 首屏最多 50 条。状态显示 `Links generated` / `Preparation failed` / `Preparation pending`。有 `Email verified:` 掩码。页面写明记录不代表文件已保存。下一页请求带 `before_id` |
| 下载和历史 | ADM-DL-028 | P1 | 中途文件失败 | 浏览器拦截第二个下载，或第二个 URL 失效 | 完成验证，让第一个文件成功、第二个失败 | 页面停在错误 alert，不再请求第三个文件。历史仍可能是 `Links generated` |
| 下载和历史 | ADM-DL-029 | P2 | 链接过期后续文件停止 | 把返回的 `expires_at` 改成已经过去，或等到 30 分钟后再继续 | 观察后续文件 | 不再下载，文案 `Download links expired. Select the remaining episodes and download again.` |
| 下载和历史 | ADM-DL-030 | P1 | 撤销管理员 | 发码后、核销前把该钱包从 `admin_whitelist` 删除 | 再提交验证码，并再要一次码 | 两次都是 `403` `admin access required`，不签名 |
| 下载和历史 | ADM-DL-031 | P2 | 打到 pipeline 上的旧验证码地址 | 对 data pipeline 直连 `POST /data/admin/downloads/verification` | 看状态码 | `410`，`Please refresh the page before requesting a code.` |
| 页面细节 | ADM-DL-032 | P1 | 取消不发请求 | 对话框刚打开，还没点 Send code | 点 Cancel，或按 Escape | 对话框关闭，选择恢复可改，Network 没有 verification 请求 |
| 页面细节 | ADM-DL-033 | P1 | 不满 8 位不能提交 | 码已发出 | 输入 7 位数字，再粘贴带字母的内容 | Verify 保持禁用。输入框里只剩数字且不超过 8 位 |
| 页面细节 | ADM-DL-034 | P2 | 请求进行中不能用 Escape 关掉 | Send code 或 Verify 的请求还没返回 | 按 Escape | 对话框仍在 |
| 页面细节 | ADM-DL-035 | P1 | 生产基址 | 用 `https://app.prismax.ai` 打开 | 完成一次发码和下载，看两个请求的 host | 发码是 `user.prismaxserver.com`。下载和历史是 `app-prismax-data-pipeline-1053158761087.us-west1.run.app` |
| 页面细节 | ADM-DL-036 | P1 | Beta 基址 | 用 `https://beta-app.prismax.ai` 打开 | 同样抓包 | 发码是 `beta-user.prismaxserver.com`。下载和历史是 beta 的 data pipeline Cloud Run。Beta 的码在生产 pipeline 上核销失败 |

---

## 9. 发布前检查

- [ ] 四个 SQL 已按顺序在目标库执行，收件人约束包含 `jason`、`bayley`、`chris`（P0）
- [ ] 用户服务和 data pipeline 使用同一套 `JWT_SECRET_KEY`，否则验证码摘要对不上（P0）
- [ ] Beta / 生产的 `K_SERVICE` 能映射到对应的 pipeline 服务名（P0）
- [ ] 三个固定邮箱能收到码，响应和历史里没有完整邮箱、没有明文码（P0）
- [ ] 错码 5 次锁定、旧码不能重放、换选择或换登录不能核销（P0）
- [ ] 生产下载走 Cloud Run 直连，不走 `data.prismaxserver.com`（P0）
- [ ] 最多 30 条；失败视图不能选；不可见任务的成功数据仍可列出并下载（P0）
- [ ] 历史只返回当前管理员，且不把签名 URL 存进下载表（P0）
- [ ] 准备失败会作废验证码，并把审计记成 `FAILED`（P1）
