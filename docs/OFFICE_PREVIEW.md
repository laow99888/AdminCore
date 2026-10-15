# Office 安全转换预览（可选）

默认关闭。只有 full 构建同时启用 `files`、`tasks`，并配置经审查的 `image@sha256:<64位摘要>`，接口才提供此能力。关闭时普通上传、下载、图片/PDF 预览照常工作；minimal 构建不能开启转换。

应用只读取存储里的文件字节，登记任务并接收 PDF，不执行外部命令、不接收外部 URL，也不挂载 Docker socket。宿主 `scripts/office_preview_runner.py` 是受信任运维组件，需要本机 Docker 权限；它通过固定的 `docker compose exec -T backend ... office_queue` 管道领取任务，逐任务创建隔离转换容器。不要把该执行器放进 backend/worker 容器。

## 支持范围与上限

仅支持 `docx/xlsx/pptx/odt/ods/odp` 的无宏、无加密、无嵌入可执行对象 ZIP 文档。旧版 `doc/xls/ppt`、启用宏的扩展名及密码文档需下载后使用本地受信任软件查看。保守检查可能拒绝包含脚本事件或嵌入对象的合法文档，不自动降级到更宽松转换。

| 项目 | 上限 |
|---|---|
| 实际读取源文件 | 10 MiB，每次从 Storage 流式有界读取，不依赖本地 path |
| ZIP | 2,000 条目；单条展开 20 MiB；总展开 50 MiB；压缩比 100 |
| 路径 | 拒绝绝对路径、反斜杠、驱动器、点路径、重复名称、符号链接；不解压到宿主 |
| 同一用户活跃任务 | 3 个 |
| 转换容器 | 网络 none；UID/GID 65532；只读根；cap-drop ALL；no-new-privileges |
| 资源 | 1 CPU；768 MiB 内存/总交换上限；96 PID；128 文件描述符；12 MiB 单文件上限 |
| 工作目录 | 独立 128 MiB tmpfs，noexec/nosuid/nodev；每任务独立输入卷，仅含单个源文件，只读 |
| 时间 | LibreOffice 60 秒；宿主等待输出 75 秒；领取令牌 120 秒有效 |
| PDF | 10 MiB、100 页；重新生成仅页面绘制属性的 PDF，再通过现有严格 PDF 检查 |
| 保留 | 等待任务有效 15 分钟；成功 PDF 自生成起再保留 15 分钟 |

转换 profile 每次创建，宏安全级别为 Very High，信任来源为空。即使文档内存在外部链接，转换容器也没有网络；图片、字体、公式、分页和打印区域可能与用户本机 Office 不同。PDF 投影会去掉链接、注解、表单等交互对象。前端使用现有 PDF.js 画布显示，不嵌入文档 HTML。

提交、领取、完成、读取均复核原始 actor、JWT session、session_version、`file:download`、数据范围、文件 lifecycle_version 和实际源 SHA-256。完成还验证单次领取令牌、有效期、引擎摘要；取消后不能发布迟到结果。用户只能访问自己的作业。结果与审计不包含源文件名、字节、存储位置或令牌；PDF 接口始终私有 no-store，没有公开对象 URL。

## 构建和启用

先阅读 `office-converter/Dockerfile`。LibreOffice writer/calc/impress 固定为 Debian trixie 的 `4:25.2.3-2+deb13u8`，镜像包含中日韩字体。镜像内 `/usr/share/admincore-packages.txt` 记录实际包版本，保留 Debian 各包的 `/usr/share/doc/*/copyright`。基础镜像构建标签会更新，因此正式启用固定最终仓库摘要，升级版本后重跑文档样本。

在受控环境中构建、扫描、测试，并发布到组织管理的仓库。以下名称是占位示例，使用自己的仓库：

```powershell
docker build --pull -t registry.example.com/admincore/office:reviewed ./office-converter
docker push registry.example.com/admincore/office:reviewed
docker image inspect registry.example.com/admincore/office:reviewed --format '{{json .RepoDigests}}'
```

从实际 RepoDigests 取得 `registry.example.com/admincore/office@sha256:...`。本地构建产生的 image ID 不是仓库 digest，不能手工拼接冒充。配置环境变量并按项目已有流程重建/重启 backend；不要把凭据写入文档或 Git：

```dotenv
ADMINCORE_OFFICE_PREVIEW_ENABLED=True
ADMINCORE_OFFICE_IMAGE=registry.example.com/admincore/office@sha256:<真实64位仓库摘要>
```

在项目根目录用受限的独立运维账户运行，参数须与应用配置相同：

```powershell
python scripts/office_preview_runner.py --image registry.example.com/admincore/office@sha256:<真实64位仓库摘要>
```

`--once` 只尝试领取一个作业，适合验收。持续运行每三秒轮询；多个执行器依赖数据库行锁竞争，不共享转换目录。让服务管理器监督执行器，记录其 PID 并只停止自己的进程。执行器不启动监听端口。

## 到期和失败清理

每次领取前处理最多 100 条到期登记，或显式执行 `docker compose exec -T backend python manage.py office_queue cleanup`。清理始终可运行，即使转换开关已经关闭。只允许删除登记的 `office-preview/<作业UUID>/preview.pdf`，不扫描其他对象、不删除原文件、不按前缀清空桶。Storage 删除失败会保留登记以便重试。

到期立即禁止 API 读取；物理删除由持续执行器/显式 cleanup 完成。执行器离线期间对象会暂时保留，因此停用前应继续运行 cleanup 直至到期对象清完，不能把“停止执行器”当作完成清理。任务历史被删除后，清理登记仍保留，到期删除产物后再删除游离登记。领取超时标记失败，不自动重新执行未知转换。

输入通过 Docker API 复制到每任务独立卷，兼容 Windows/WSL 及远程引擎；复制用的容器从不启动，转换器只读挂载该卷。每次转换均尝试强制删除本作业随机容器、复制容器和输入卷，失败时只对该名称重试一次，仍无法确认则停止领取。失败报告只保留作业 UUID、固定错误码，以及必要时本任务资源名；临时源字节总会删除。报告位于本任务 `admincore-office-<作业UUID>-...` 临时目录。检查原因后只处理报告中明确记录的资源；不要使用全局 prune 或按进程名批量停止。成功任务会删除自己的临时目录。

## 验收要求

单元测试不代表真实 LibreOffice 转换验收。启用前在一次性独立数据库、独立 media/对象桶和独立 compose 项目完成：

1. 六种格式各提供可实际打开的文档，包含中文、表格和分页；验证完整提交→领取→转换→私有 PDF→前端画布路径。单元测试中的最小 ZIP 只验证格式/安全边界，不能用作排版样本。
2. 验证已有图片和 PDF 预览仍工作，默认关闭和 minimal 构建不显示 Office 操作。
3. 含链接的正常文档可投影成安全 PDF；宏、加密、损坏、ZIP 炸弹、路径穿越和实体声明文档拒绝；容器外链无网络，且没有 Docker socket/宿主目录访问。
4. 转换中取消、会话撤销、权限/数据范围变化、源版本/字节变化、引擎摘要变化，完成/读取均拒绝；重复令牌不能完成第二次。
5. 超时、转换器退出、超大 PDF、Storage 故障以及 Docker 清理故障都应留下固定错误和可定位证据；恢复后只清理本测试登记和容器。
6. 先验证本地私有存储，再验证配置的 S3 私有存储，确认无 `.path` 依赖、无公开 URL、完整性校验和到期删除有效；删除任务历史后仍能清理产物。
7. 观察单任务 CPU/内存与 10 MiB 文档耗时。当前逐任务启动优先隔离；大文件、并发吞吐和复杂排版需依据部署资源另行验收，不能承诺与桌面 Office 完全一致。

自动检查入口：

```powershell
cd backend
./venv/Scripts/python.exe -m pytest tests/test_office_preview.py ../scripts/tests/test_office_preview_runner.py -o addopts='' -q
cd ../frontend
npm test -- --run tests/office-preview-api.test.ts tests/file-preview-api.test.ts
npm exec vue-tsc -- --noEmit
```

一次性真实集成验收由 `scripts/validate_office_preview.py` 创建随机独立 project/PG/环境；仅读自己生成的环境，不读取源 `.env`。接受已审查的仓库摘要和已提交版本，成功移除本次项目/卷/网络与临时资料，失败停止本次项目并保留报告。它用真实 LibreOffice 将三个含内容的 ODF 生成对应 OOXML，然后六格式经真实 HTTP/JWT/队列/容器转换，检查 PDF 文本和安全投影，同时覆盖撤权、源变化、取消、失联和清理：

```powershell
./backend/venv/Scripts/python.exe scripts/validate_office_preview.py --image registry.example.com/admincore/office@sha256:<真实64位仓库摘要> --ref <已提交版本> --frontend-port 18620 --backend-port 18621
```

浏览器交互专项为 `frontend/e2e/office-preview.spec.ts`，按项目 Playwright 流程在已构建前端上验收桌面与窄屏；它使用隔离 API 路由和真实 PDF.js worker，不能替代上述真实后端/转换器验收。

GitHub Actions 的独立 `office-preview` 作业执行上述真实六格式验收，最长30分钟。宿主仅安装 Python 3.13.15 和已有哈希依赖锁；项目工具在 Docker 内构建 backend/frontend，无需宿主 Node。作业以 `office-converter/Dockerfile` 固定的 LibreOffice 包构建镜像，推送到仅绑定 `127.0.0.1:18590` 的专属 `registry:3.0.0`，从实际 `RepoDigests` 取得摘要后调用 `--ref HEAD`；项目接口仅绑定本机18620/18621。转换容器继续使用 `network none`。

CI始终上传明确列出的 `report.json`、`runner.log`、`project-start.log`，不上传生成的项目.env、凭据或整个临时目录。验收脚本成功时按归属移除自己的项目，失败时停止并保留项目证据；CI另在always步骤校验专属名称和标签，移除本作业registry容器及其匿名卷。没有全局prune或按进程名清理。该CI接线需在最终提交后的远端运行确认，不能把本地YAML检查当成真实转换通过。

真实 S3 组合使用已有独立 MinIO 进程验收入口：`./backend/venv/Scripts/python.exe scripts/validate_storage.py --office-image <已审查image@sha256>`。此可选模式额外运行 `backend/integration/test_s3_office_preview.py`：真 JWT、MinIO 私有源和派生 PDF、真实隔离 LibreOffice 转换、PDF 文本、匿名桶访问拒绝、S3 源内容变化拒绝，以及历史删除后的 TTL 清理；不会使用正式桶。常规不传参数仍只跑原存储合同。

官方依据：[LibreOffice 启动参数](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html)、[宏安全级别](https://help.libreoffice.org/latest/en-US/text/shared/optionen/macrosecurity_sl.html)、[Debian LibreOffice 包](https://packages.debian.org/trixie/libreoffice-core)、[Docker none 网络](https://docs.docker.com/engine/network/drivers/none/)、[Docker 容器资源与权限参数](https://docs.docker.com/reference/cli/docker/container/run/)、[LibreOffice 许可证](https://www.libreoffice.org/about-us/licenses/)。
