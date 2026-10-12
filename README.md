# AdminCore - 中后台系统基础框架

现代化、专业级的中后台管理系统基座。包含完整的前后端框架、权限系统、文件管理、数据导入导出、任务调度等通用功能。

## 项目特点

- 🎨 **设计规范优先**：青色 + 石板灰、明暗双主题、Element Plus 完全适配
- 🔐 **企业级权限**：JWT 认证 + RBAC + 细粒度权限控制
- 📊 **完整基础设施**：文件系统、数据导入导出、任务调度、审批流程、审计日志
- 🚀 **部署目标**：Docker Compose 启动完整环境
- 📚 **文档完整**：快速开始、开发规范、API 文档、部署指南

## 快速开始

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

#### 方式 B：本地分进程启动

```bash
# 后端
cd backend
python -m venv venv
# Windows PowerShell：.\venv\Scripts\Activate.ps1
# Linux Bash：source venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python manage.py migrate
python manage.py bootstrap_admincore           # 使用明确配置的管理员密码初始化
python manage.py runserver 0.0.0.0:8000

# 前端
cd frontend
npm ci
npm run dev
```

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

- [快速开始](./docs/快速开始.md)
- [后端开发指南](./docs/后端开发指南.md)
- [API 规范](./docs/API规范.md)
- [部署指南](./docs/部署指南.md)

## 项目状态

阶段三（功能集成）已完成，阶段四（部署与文档）基本完成。详见 [功能清单](./功能清单.md)。

## 许可证

MIT
