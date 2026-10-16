# OpenAPI 与 TypeScript SDK

P2-13 提供从实际 Django URL/DRF serializer 生成契约、路由映射和 TypeScript 类型的工具，以及复用现有 Axios 的调用入口。生成器固定为 `openapi-typescript 7.13.0`，位于开发依赖；原清单的 `openapi-generator` 是工具候选，本实现采用上述生成器完成同一功能，没有安装 Java 版 openapi-generator。

## 生成与检查

先按根目录版本基线安装后端完整哈希锁和前端 `npm ci`，在 `frontend` 执行：

```powershell
npm run sdk:generate
npm run sdk:check
npm run test:typecheck
```

默认生成 `src/api/generated/openapi.json`、`schema.ts` 和 `routes.ts`。三者均提交 Git；修改后端接口、serializer、operationId 或模块 URL 后须重新生成。不要手改生成文件。`sdk:check` 重新导出并逐文件比较，允许 Windows/Linux 换行差异；任何 schema、类型或路由漂移都失败。独立 `sdk-contract` CI 同时执行漂移检查、类型正反例、调用测试和导出测试。

默认 full 契约显式启用全部登记模块，包含本批 13 个模块、155 条路径，表示可安装能力合集。它不代表部署已启用全部能力。运行环境仍按模块开关、权限和数据范围决定是否允许访问；接口关闭返回原有错误，不由 SDK 绕过。

导出使用隔离测试配置，不读取 `.env`、部署数据库或供应商配置，不访问线上 `/schema/`。自定义契约必须显式指定输出目录，防止误覆盖仓库 full 契约：

```powershell
npm run sdk:generate -- --profile minimal --output-dir ../.codex-validation/sdk-minimal
npm run sdk:generate -- --modules files --output-dir ../.codex-validation/sdk-files
npm run sdk:check -- --modules files --output-dir ../.codex-validation/sdk-files
```

`standard` 按现有标准预设导出；`--modules` 覆盖模块列表并沿用现有依赖检查。未知模块或外部 `$ref` 会拒绝导出。Python 优先使用 `ADMINCORE_PYTHON`，其次项目 `backend/venv`，最后系统 Python；该变量只指定本机解释器路径，不写入生成文件。

## 调用

```typescript
import { sdk } from '@/api/sdk'

const result = await sdk('tasks_backups_retrieve', {
  signal: controller.signal,
})
const enabled: boolean = result.data.enabled

await sdk('files_create', {
  contentType: 'multipart/form-data',
  body: { file: selectedFile, description: '合同' },
})

const file: Blob = await sdk('files_download_retrieve', {
  path: { id: fileId }, responseType: 'blob',
})
```

方法和 URL 来自生成的 operationId 映射；路径参数、查询、请求体及响应来自同一契约。JSON 默认不需指定 contentType；表单须明确选择契约中的媒体类型，上传字段为 Blob/File，multipart boundary 交给适配器。查询数组使用重复键。二进制响应必须显式选择 `responseType: 'blob'`，204/205 规范化为 `undefined`。SSE 继续使用已有实时客户端。

调用沿用现有 Axios 的 API base URL、认证、语言、会话刷新及错误处理。SDK 不另外重试；既有 401 会话刷新行为仍适用。路径替换会编码并拒绝分隔符、控制字符、缺失及多余参数；operationId 必须来自固定登记表，不接收任意请求地址。

`backups.ts` 的四个实际接口已切换为 SDK 调用，状态与备份产物类型直接引用生成契约。其他已有手写 API 可逐项迁移，不要求一次重写。后端备份产物及恢复历史的嵌套 serializer 同步具体化，避免生成类型退化为任意 JSON。

类型检查包含十项编译失败反例，涵盖不存在操作、参数名称/类型、缺少密码、额外请求字段、上传和下载类型。TypeScript 只约束编译期使用，业务权限、配置和运行时输入校验仍由后端执行；SDK 不提供额外的运行时 schema 校验。

## 本批验收（2026-10-17）

- 离线导出、环境隔离、full/minimal/files 启停、确定性和三类漂移检查：5 项通过。
- SDK 调用、上传、下载、取消、路径边界和空响应：17 项；最终前端全量 422 项/53 文件通过，lint、类型正反例检查通过。
- 备份、任务、API 生命周期与模块相关后端：108 项通过。
- 最终后端全量：1,849 项通过、3 项跳过；跳过的专属场景由对应隔离任务分别验收，不将 SQLite 结果当作 PostgreSQL 行锁证明。
- 完整生产构建和 bundle 门槛通过；登录初始 JS gzip 183,211 字节，未放宽 180 KiB 预算。SDK 路由表由业务页面加载，不进入登录首屏。
- 备份与 IP 策略桌面/手机浏览器回归：16 项通过，使用 API fixture；不是本批重新执行真实宿主恢复。

代码提交 `1041133` 的[远端项目检查](https://github.com/laow99888/AdminCore/actions/runs/38929604356)已全部通过（17/17），包含独立 SDK 门禁、精简构建、前后端与完整浏览器回归、真实 PostgreSQL/存储/Office/备份等任务；[HTTP 性能回归](https://github.com/laow99888/AdminCore/actions/runs/38929604498)也成功。这里只记录该代码提交的实测结果，不代表公网容量或生产部署已重新验收。
