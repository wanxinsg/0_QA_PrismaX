# Sprint 24 Review：生产订单接口被 Cloudflare 挡下

> 日期：2026-09-24（UTC+8）  
> 范围：`prismax-marketing-rp`、`app-prismax-rp-backend`（user management）  
> 现象：订单 API 在 beta 正常，在生产失败。  
> 相关提交：营销站 `ca4a2d0`、`5a38895`；用户 API `50054d2`。同类先例：营销站 `75cee67`（数据管道公网域名）。

## 1. 发生场景

用户在生产营销站打开 Robotics Data 的订单页。页面请求订单接口时，浏览器打的是营销站自己的同源路径 `/prismax-user/api/...`。Next.js 在服务端把这条路径 rewrite 到用户管理服务。

生产 rewrite 的上游是公网域名 `https://user.prismaxserver.com`。这个域名在 Cloudflare 后面，并且开了浏览器验证。Next 的服务端转发不是浏览器请求，Cloudflare 回的是 HTML challenge，不是 JSON。订单客户端按 JSON 解析，订单列表和其他订单操作失败。

Beta 走同一条 `/prismax-user` 代理，但上游在 `next.config.ts` 里已经写成 Cloud Run 地址 `app-prismax-backend-beta-....run.app`。公网域名 `https://beta-user.prismaxserver.com` 那一行是注释掉的。服务端请求不经过 Cloudflare，直接拿到 JSON，所以 beta 没有这个问题。

```35:41:prismax-marketing-rp/next.config.ts
const DEFAULT_USER_MANAGEMENT_ORIGIN =
  IS_LOCAL_DEVELOPMENT
    ? "http://127.0.0.1:8080"
    : IS_BETA_DEPLOYMENT
      // ? "https://beta-user.prismaxserver.com"
      ? "https://app-prismax-backend-beta-1053158761087.us-west1.run.app"
      : "https://user.prismaxserver.com";
```

数据管道在 2026-08-12 出现过同一类故障。当时生产 `/prismax-data` 的上游是 `https://data.prismaxserver.com`。公网域名的浏览器验证拒绝了 Next 服务端代理，机器人数据页拿不到 JSON。`75cee67` 把生产上游改成 `app-prismax-data-pipeline-....run.app`。Beta 数据管道当时已经是 Cloud Run 地址。公网域名仍给浏览器和外部客户端用，不再当作服务端代理的上游。

## 2. Root cause

生产用户 API 的服务端代理仍指向带 Cloudflare 浏览器验证的公网域名。Beta 已经改成直连 Cloud Run，生产漏改，和数据管道修复前的配置差一截。

Cloudflare 对浏览器放行，对 Next rewrite 返回 HTML。订单接口把这段 HTML 当 JSON 解析后失败。失败只出现在「营销站服务端代发 + 生产公网域名」这条链路上。浏览器直接打开 `user.prismaxserver.com`，或 beta 代理打 Cloud Run，都不会走到这个失败点。

## 3. 解决方法

同一作者在约 40 分钟内交了三笔提交。前一笔修代理上游，后两笔改成浏览器直连，并补上生产页面的 CORS。订单最终走的是后一种。

| 时间 (UTC+8) | 仓库 | Hash | 说明 |
| --- | --- | --- | --- |
| 09-24 05:17 | prismax-marketing-rp | `ca4a2d0` | 构建时解析 User Management 的 Cloud Run URL，写入 `USER_MANAGEMENT_ORIGIN`；非 JSON 响应给出明确错误 |
| 09-24 06:01 | prismax-marketing-rp | `5a38895` | 订单改为浏览器调用 `getUserApiBase()` |
| 09-24 06:01 | app-prismax-rp-backend | `50054d2` | 用户 API 生产 CORS 增加 `https://prismax.ai` |

### 3.1 `ca4a2d0`：代理改打 Cloud Run

Cloud Build 在镜像构建前执行 `gcloud run services describe`，区域 `us-west1`。`testing` 分支或 `_PRISMAX_ENV=beta` 取 `app-prismax-backend-beta`，否则取 `app-prismax-backend`。结果通过 Docker build-arg `USER_MANAGEMENT_ORIGIN` 写进镜像，供 `/prismax-user/:path*` rewrite 使用。`_USER_MANAGEMENT_ORIGIN` 非空时跳过自动发现。

`orderApi.ts` 先看 `Content-Type`。响应不是 JSON 时不再调用 `response.json()`，错误文案为 `Order service returned HTTP {status} instead of JSON.`

这一步的意图和数据管道的 `75cee67` 相同：服务端代理绕开 Cloudflare。构建账号需要 `run.services.get`。`describe` 失败或结果文件为空时，整次构建停止。

### 3.2 `5a38895`：订单改为浏览器直连

`orderApi.ts` 去掉 `ORDER_API_BASE = "/prismax-user"`，请求改为 `getUserApiBase() + path`。页面上的 reported-episodes 示例和对应测试一起改了。

浏览器里的地址：

| 页面环境 | 订单请求目标 |
| --- | --- |
| localhost | `http://127.0.0.1:8080` |
| beta | `https://beta-user.prismaxserver.com` |
| 生产 | `https://user.prismaxserver.com` |

这和账号、waitlist、contact sales 已有的调用方式一致。浏览器能通过 Cloudflare 验证，订单不再依赖上一笔提交修的那条代理。`ca4a2d0` 里的 JSON 判断保留，公网偶发返回 HTML 时错误更清楚。

`getUserApiBase()` 在服务端固定返回生产域名 `https://user.prismaxserver.com`。订单页是 client component，请求发生在浏览器。

### 3.3 `50054d2`：补上 apex 域名的 CORS

浏览器直连之后，请求从营销站页面跨域打到用户 API，预检要带页面的 `Origin`。

生产营销站 origin 是 `https://prismax.ai`（见 `deploymentUrls.mjs`）。用户 API 生产 CORS 里原来有 `https://www.prismax.ai` 和 `https://beta-www.prismax.ai`，没有 apex。flask-cors 按完整 origin 匹配，`www` 不会覆盖 `https://prismax.ai`，apex 上的订单预检会被拒绝。Beta 页面是 `https://beta-www.prismax.ai`，本来就在白名单里。

`50054d2` 在 `app_prismax_user_management/app.py` 的生产 `origins` 中加入 `https://prismax.ai`。测试模式仍是 `origins: "*"`。

### 3.4 三笔合在一起之后

订单请求不再经过 `/prismax-user`。Cloud Build 解析出的 Cloud Run origin 仍服务于这条 rewrite。仓库里还在用它的是 `BetaAccessGate`（`/prismax-user/auth/beta`）。

`README.md` 仍写着这个 origin 是为了修 Orders。订单路径已经改成浏览器直连，这段说明和当前代码不一致。

## 4. 对将来的建议

1. 营销站里凡是 Next 服务端 rewrite 的上游，使用对应 Cloud Run URL。`*.prismaxserver.com` 留给浏览器和外部客户端。新增一条代理时，对照 `/prismax-data` 的写法，beta 和生产一起改。
2. 改 beta 或生产其中一边的 origin 时，打开 `next.config.ts` 把另一边的默认值对一下。这次就是 beta 已改 Cloud Run、生产仍留公网域名。
3. 前端从「同源代理」改成「浏览器直连公网 API」时，把真实页面 origin 加进该 API 的 CORS。生产要覆盖 `https://prismax.ai` 和 `https://www.prismax.ai`，beta 要覆盖 `https://beta-www.prismax.ai`。用 beta 或 www 通过，不能代替 apex 生产域名。
4. 一条故障确定一种请求路径后再合入。若最终采用浏览器直连，同步改 README，避免文档仍要求用 Cloud Run origin 修 Orders。`/prismax-user` 还被 Beta Access 使用，那条 rewrite 的 Cloud Run 上游需要保留，并在生产镜像里确认 `USER_MANAGEMENT_ORIGIN` 已写入。
5. 回归时在生产页面 `https://prismax.ai` 上打开订单，确认接口返回 JSON，并确认预检响应允许该 origin。Beta 通过只能说明 beta 上游和 beta origin 正常。
6. 保留「非 JSON 则报 HTTP 状态而不是解析失败」这类判断。它能把 Cloudflare HTML 和真正的接口错误分开。
