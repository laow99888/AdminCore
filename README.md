# AdminCore - 中后台系统基础框架

现代化、专业级的中后台管理系统基座。包含完整的前后端框架、权限系统、文件管理、数据导入导出、任务调度等通用功能。

**AI 接手从 [AGENTS.md](AGENTS.md) 开始**，按 [任务导航](docs/ai/README.md) 找到对应 [能力、代码与测试](docs/ai/能力地图.md)。整体调用链见 [系统结构](项目结构说明.md)，业务新增按 [开发流程](docs/ai/业务开发流程.md)。不需要先通读历史审计报告。

首个正式版本准备为 **v1.0.0**；实际发布状态与采用方式见 [发布策略](docs/发布与版本策略.md) 和 [Releases](https://github.com/laow99888/AdminCore/releases)。下游业务版本与底座版本独立管理。

## 项目特点

- 🎨 **设计规范优先**：青色 + 石板灰、明暗双主题、Element Plus 完全适配
- 🔐 **企业级权限**：JWT 认证 + RBAC + 细粒度权限控制
- 📊 **完整基础设施**：文件系统、数据导入导出、任务调度、审批流程、审计日志
- 🚀 **部署目标**：Docker Compose 启动完整环境
- 📚 **文档完整**：快速开始、开发规范、API 文档、部署指南

## 快速开始

要创建独立业务项目，可使用 `python scripts/create_project.py D:/Projects/my-admin --name my-admin --start`，从已提交源码导出并启动精简预设，生成独立随机凭据。目标必须是仓库外的新目录；标准版增加 `--preset standard`。详见[初始化及升级方法](docs/底座版本与项目升级.md)。

### 本地开发环境

先按 [版本要求.md](版本要求.md) 安装固定版本。完整步骤见 [快速开始](./docs/快速开始.md)。

#### 方式 A：Docker Compose 一键启动（推荐）

```bash
# 1. 准备环境变量（必改 DJANGO_SECRET_KEY、DB_PASSWORD、ADMINCORE_ADMIN_PASSWORD）
cp .env.example .env

# 2. 构建并启动（首次自动迁移 + 初始化权限及管理员）
docker compose up -d --build

# 3. 健康检查
bash scripts/health_check.sh
```

访问 http://localhost （Nginx 前端 + API 反代）。使用 `.env` 中明确设置的管理员账号和密码登录；生产环境不创建演示账号。

小项目可选物理精简构建：`docker compose -f docker-compose.yml -f compose.minimal.yml -f compose.build-minimal.yml up -d --build db backend frontend`，只启动三服务，并裁剪可选 Python 依赖和业务前端资源。恢复完整能力须移除精简覆盖、同步重建前后端并保留数据卷；运行时启停与构建裁剪的区别见[精简构建](docs/精简构建与完整恢复-2026-10-15.md)。

企业登录和 Office 转换均为可选能力，默认关闭。配置、支持范围和执行器部署分别见[企业 OIDC 登录](docs/企业OIDC登录与显式身份绑定-2026-10-16.md)与[Office 预览](docs/OFFICE_PREVIEW.md)；小项目可以保留关闭状态。

#### 方式 B：本地分进程启动

```bash
# 后端
cd backend
python -m venv venv
# Windows PowerShell：.\venv\Scripts\Activate.ps1
# Linux Bash：source venv/bin/activate
python -m pip install --require-hashes -r requirements.dev.lock
DJANGO_ENV=development python manage.py migrate
DJANGO_ENV=development python manage.py bootstrap_admincore  # 使用明确配置的管理员密码初始化
DJANGO_ENV=development python manage.py runserver 127.0.0.1:8000

# 前端
cd frontend
npm ci
npm run dev
```

以上命令采用 Bash 环境变量语法；PowerShell 先执行 `$env:DJANGO_ENV="development"`，随后直接运行 `python manage.py ...`。通用 settings 入口必须明确选择环境，拼错或遗漏会拒绝启动。

访问 http://localhost:5173

## 技术栈

| 层 | 技术 | 固定版本 |
|---|---|---|
| 运行时 | Python / Node.js / npm | 3.13.15 / 24.21.0 / 11.19.0 |
| 后端 | Django LTS / DRF | 5.2.18 / 3.18.3 |
| 前端 | Vue / TypeScript | 3.5.43 / 5.9.3 |
| 构建 | Vite | 8.3.4 |
| UI 库 | Element Plus | 2.14.7 |
| 状态管理 | Pinia | 3.0.4 |
| 数据库目标 | PostgreSQL | 18.6 |
| 缓存/队列目标 | Redis | 8.10.2 |
| 任务调度 | Celery / Django Celery Beat | 5.6.3 / 2.9.0 |

完整基线、安装步骤与更新策略见 [版本要求.md](版本要求.md)；实际验证范围和当前阻塞项见 [COMPATIBILITY.md](COMPATIBILITY.md)。

## 文档

- [AI 任务导航与开发手册](docs/ai/README.md)
- [系统结构与调用链](项目结构说明.md)
- [工程约束](docs/ai/工程约束.md)
- [分层验证与交付](docs/ai/验证与交付.md)
- [发布与版本策略](docs/发布与版本策略.md)

- [快速开始](./docs/快速开始.md)
- [后端开发指南](./docs/后端开发指南.md)
- [API 规范](./docs/API规范.md)
- [OpenAPI 与 TypeScript SDK](./docs/OpenAPI与TypeScript%20SDK.md)
- [部署指南](./docs/部署指南.md)
- [模块启停、预设及组织/参数/字典/品牌](./docs/模块与基础能力.md)

## 项目状态

通用基础版与多批扩展能力已交付，包括图片/PDF 预览、认证邮件、设备会话、TOTP 和可选登录验证码。模板化业务邮件及可选短信/Webhook、OIDC 登录和可选 Office 转换已提供；多级审批支持串行节点、会签、或签、加签、转交、委托与抄送；完整实施状态见 [通用基座缺口清单](./docs/通用基座缺口清单.md)。用户管理联系方式默认脱敏，手机号存储加密可按部署选择启用，详见 [敏感字段边界与配置](./docs/敏感字段脱敏与可选加密-2026-10-14.md)。

公告提供可选富文本编辑、预览和前后端白名单消毒，历史公告默认保持纯文本；可复用组件、支持范围和升级注意见 [富文本公告与安全渲染](./docs/富文本公告与安全渲染-2026-10-14.md)。

前端已提供 `npm run test:typecheck`、`npm run test:coverage`、`npm run test:e2e` 和构建后的 `npm run check:bundle`；CI 执行这些检查。后端大数据基准脚本在 `backend/benchmarks/list_api.py`，只允许使用独立的指定测试数据库，运行说明见验收报告。

本轮集中审查修复的范围、异步删除语义和实际验证结果见[集中修复验收记录](docs/集中审查修复验收-2026-10-16.md)。

## 许可证

MIT
