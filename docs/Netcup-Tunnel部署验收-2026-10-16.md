# Netcup / Cloudflare Tunnel 测试部署验收

2026-10-16：已将应用提交 `af4adf120e5cbf4dd465da568850ccb2516d4790` 部署到独立测试环境，公网入口为 <https://admincore-test.iiiu.im>。这是新数据库，不包含 Windows 原环境的业务数据。后续仅补充本文档不会改变服务器上运行的应用镜像版本。

## 部署边界

- 服务目录 `/opt/admincore`，源码 `/opt/admincore/releases/af4adf120e5c`，`current` 指向此版本。
- 独立 Compose 项目 `admincore-test`，六服务为 backend、frontend、worker、beat、db、redis。资源设置了各自的内存、CPU、进程数上限，worker 并发 1。
- Docker 网络 `10.203.87.0/24`，直接网关 `10.203.87.1`；与既有 Docker 网络、主机路由检查无冲突。
- 仅发布 `127.0.0.1:18087 → frontend:80`，后端、数据库、Redis 不发布宿主端口。Tunnel 回源 `http://127.0.0.1:18087`，公网 TLS 在 Cloudflare 边缘终结。
- Nginx 仅信任直接网关的协议与客户端转发头。HTTP 明确跳转固定 HTTPS 域名，私有媒体不能直接下载。
- 环境及初始化凭据分别保存在服务器 `.env`、`admin-access.txt`，权限均为 `600`；未纳入 Git。Windows 交付副本保存在工作区外，ACL 仅当前管理员可访问。不要将其作为故障日志上传。
- 只有一个有效管理员，无 demo 账号，公开注册关闭。初始密码为独立生成的强密码，首次登录必须修改；初始化环境值不会覆盖已有管理员之后设置的密码。

## 实际通过的检查

| 范围 | 结果 |
| --- | --- |
| 服务内部 | 29 项通过：真实 PostgreSQL/Redis 健康、worker pong、迁移及系统检查、SPA 安全头、HTTP 跳转、非可信容器伪造协议头拒绝、真实登录/首次改密业务保护/退出令牌撤销、网络与端口边界等 |
| 运行镜像 | backend、worker、beat 的 291 份 Python 源码分别与该发布源码 SHA-256 一致 |
| 原有业务 | 部署前记录的 46 个容器仍为原容器且运行；未替换原网站、代理、Tunnel 或其他业务容器 |
| 公网链路 | 18 项通过：系统信任库验证证书链和域名、HTTP 跳转保留路径查询、公网伪造协议头不能降级或绕过跳转、当前发布标识、JS 资源、安全响应头、依赖健康、匿名私有 API/媒体拒绝、真实管理员登录/改密保护/退出撤销 |
| 实际浏览器 | Chromium 桌面 1440×1000、手机 375×667：匿名登录页、真实登录、强制改密页、退出及本地凭据清理均通过；无横向溢出、未捕获脚本错误或 HTTP 5xx；截图已目视核对 |

浏览器验收没有替用户修改个人密码，所有本次成功创建的验收会话已退出。未在此测试库重新执行先前的完整业务回归或容量压测，不以部署冒烟替代既有专项验收。

用户自行修改密码后，另完成[公网登录后详细验收](公网登录后详细验收-2026-10-16.md)：桌面和手机 56 次页面访问、54 条业务及收尾断言通过；发现审计 IP、顶部搜索、投递记录空操作插槽 3 项待修缺陷及 1 项翻译瑕疵。该轮是有保留的业务验收，没有修改应用代码。

## TLS、HSTS 与仍待确认的续期

公网协商 TLS 1.3，系统证书验证通过；证书签发者 Google Trust Services / WE1，SAN 包含 `iiiu.im` 与 `*.iiiu.im`，有效期至 **2026-11-16 11:15:45 UTC**。2026-10-16 08:45 UTC 完成公网检查。该证书由当前 Cloudflare 边缘返回；不需要为本机 HTTP 回源额外申请 Let's Encrypt 证书。

当前 HSTS 为 `max-age=300`，未启用 includeSubDomains / preload。`check --deploy` 成功退出，保留 `security.W005` 与 `security.W021` 两项提醒，原因是没有将测试域名的策略扩展到全部子域或浏览器预加载名单。不能为清空警告而扩大域名安全策略。

[Cloudflare 官方 Universal SSL 文档](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/)说明其自动签发、部署及续期机制。但本次未访问用户账户核对具体证书产品及配置，也没有经历真实续期周期，不能据此宣称该账户的续期已实测。**P3 对应项保留部分验收状态**：公网 TLS/HSTS、代理边界及生产检查已过，账户续期配置与跨周期结果待确认。

## 日常操作

使用部署包装器，避免遗漏环境文件、覆盖配置和项目名：

```bash
/opt/admincore/compose ps
/opt/admincore/compose logs --tail 100 backend worker beat
/opt/admincore/compose exec -T backend python manage.py migrate --check
curl --fail https://admincore-test.iiiu.im/api/v1/health/
```

不要直接在 `current` 目录运行默认 `docker compose`，也不要将完整 `compose config`、容器环境或 `.env` 输出到日志。此次覆盖配置单独保存在 `/opt/admincore/compose.tunnel.yml`、`nginx.tunnel.conf`、`security-headers.tunnel.conf`，包装器固定组合基础配置与这些部署覆盖。

邮件、短信、Webhook、OIDC、Office 转换和自动备份等外部能力未在本测试部署启用。仓库备份执行器需要先适配本部署显式 Compose 参数，再做自动计划、备份恢复和实际容量 RPO/RTO 验收；不能直接照搬开发环境默认命令。正式使用前应完成这一运维环节。

## 证据与收尾

服务器保留 `/opt/admincore/deployment-report.json`、`public-verification.json`、`public-browser-report.json`、`check-deploy.log`、`README-deployment.md`。

本机诊断与截图保存在忽略目录 `.codex-validation/netcup-af4adf120e5c/`，包含内部、公网、浏览器验收报告及失败脚本诊断。凭据与令牌没有写入这些报告。

本次浏览器进程随脚本退出而关闭，没有启动需要保留的开发服务器或 watcher，没有占用新增本机开发端口；六个服务器业务服务按部署要求持续运行。成功传输后的镜像压缩包、源码中转包及本机临时展开源码可清理，运行镜像、远端发布源码、证据和凭据继续保留。
