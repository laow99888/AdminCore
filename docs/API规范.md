# AdminCore API 规范

- 基础路径：`/api/v1/`
- 交互式文档（Swagger）：`/api/v1/docs/`，ReDoc：`/api/v1/redoc/`，OpenAPI Schema：`/api/v1/schema/`（drf-spectacular 自动生成）
- 实际验证状态见 [COMPATIBILITY.md](../COMPATIBILITY.md)

## 认证

JWT Bearer（Simple JWT）：

```
Authorization: Bearer <access_token>
```

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/auth/login/` | POST | 登录，返回 `{access, refresh, user}` |
| `/api/v1/auth/register/` | POST | 注册 |
| `/api/v1/auth/refresh/` | POST | 刷新 access token |
| `/api/v1/auth/logout/` | POST | 登出 |
| `/api/v1/auth/me/` | GET | 当前用户信息 |
| `/api/v1/auth/change_password/` | POST | 修改密码 |

## 统一响应格式

成功（普通动作）：`{code, message, data}`；列表分页：`data.items` + `data.pagination`（total/page/page_size/total_pages）。

错误：`{code, message, data}`，`code` 与 HTTP 状态码一致（400 参数错误、401 未认证、403 无权限、404 不存在、429 限流、500 服务器错误）。

限流：匿名 100 次/小时，认证用户 1000 次/小时。

## 端点总表

| 模块 | 路径 | 权限 | 说明 |
|---|---|---|---|
| 用户 | `/users/` | 管理员 | CRUD、`{id}/reset_password/`、`bulk_action/` |
| 角色 | `/permissions/roles/` | 管理员 | CRUD（`permission_ids` 分配权限） |
| 权限 | `/permissions/permissions/` | 认证用户 | 只读列表 |
| 菜单 | `/permissions/menus/`、`/permissions/menus/my_menu/` | 认证用户 | 菜单树 |
| 文件 | `/files/` | 认证用户 | 上传（multipart，白名单+大小限制）、列表（非管理员仅见自己）；`{id}/download/`、`{id}/purge/`（物理删除，管理员） |
| 任务 | `/tasks/` | 管理员 | 任务记录；`{id}/cancel/`、`cleanup/` |
| 通知 | `/notifications/` | 认证用户 | 我的通知；`mark_read/`、`mark_all_read/`、`unread_count/`；POST 群发（管理员） |
| 审批 | `/approvals/` | 认证用户 | `?box=todo/done/sent` 三视角；`{id}/approve/`、`{id}/reject/`、`{id}/cancel/` |
| 导入导出 | `/data-io/import/`、`/data-io/import/{task_id}/`（GET 结果 / POST 重试）、`/data-io/template/`、`/data-io/export/` | 管理员 | Excel/CSV 导入导出（导出参数用 `export_format=csv|xlsx`） |
| 日志 | `/logs/operation/`、`/logs/login/`、`/logs/exception/` | 管理员 | 只读查询 |
| 仪表盘 | `/dashboard/stats/` | 认证用户 | 统计指标 + 7 日登录趋势 + 任务状态分布 |
| 健康检查 | `/api/v1/health/` | 公开 | `{"status": "ok"}` |

## 前端对接

前端请求层在 `frontend/src/api/`（axios 拦截器自动携带 token、401 跳登录、统一错误提示）。新增接口时：

1. 后端：应用内写 view/serializer，注册到应用 `urls.py`
2. 前端：`src/api/index.ts` 补充类型与方法
3. 测试：`backend/tests/` 对应模块加用例，或扩展 `smoke_test.py`

## 示例

```bash
# 登录
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "<配置的管理员密码>"}'

# 携带 token 查询待办审批
curl http://localhost:8000/api/v1/approvals/?box=todo \
  -H "Authorization: Bearer <access>"

# 导入用户（multipart）
curl -X POST http://localhost:8000/api/v1/data-io/import/ \
  -H "Authorization: Bearer <access>" \
  -F file=@import-users.xlsx -F resource=users
```
