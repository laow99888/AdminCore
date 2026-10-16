# ClamAV 病毒扫描与验收

AdminCore 的文件扫描默认关闭，不启用时不连接 ClamAV，也不改变小项目的六服务部署。需要启用时，使用固定镜像的覆盖编排：

```powershell
docker compose -f docker-compose.yml -f docker-compose.antivirus.yml up -d --build
```

覆盖文件固定使用 `clamav/clamav:1.5.4@sha256:638d90201ee7ee6a82d249a2fc23b132e578673b5f1f2766852b127676ca1ef6`。签名库放在独立的 `clamav-signatures` 卷中，ClamAV 只通过 Compose 内网暴露 3310 端口；不要把该端口发布到公网。签名库首次下载可能需要等待容器健康检查完成。

扫描配置也可以由环境变量提供：

```dotenv
ADMINCORE_ANTIVIRUS_ENABLED=True
ADMINCORE_CLAMAV_ADDRESS=clamav
ADMINCORE_CLAMAV_PORT=3310
ADMINCORE_CLAMAV_TIMEOUT=20
ADMINCORE_CLAMAV_MAX_BYTES=52428800
```

应用使用 ClamD `zINSTREAM` 协议，以 64 KiB 分块发送，并限制总超时、单文件大小和回复长度。上传、历史文件读取、头像、导入源、水印及 Office 生成结果都经过同一检查入口；感染文件返回 422，服务不可用、协议错误或超限返回 503/413，均不会降级放行。扫描结果写入 `file_scan` 审计，日志只保留状态、摘要、大小、引擎和签名摘要，不记录文件内容或存储路径。审计失败时拒绝响应，并补偿清理本次新写入的数据库记录和存储对象。

本地真实引擎验收（需要 Docker）：

```powershell
$port = (docker port admincore-clamav-validation 3310/tcp).Split(':')[-1]
backend/venv/Scripts/python.exe scripts/validate_clamav.py --port $port
```

脚本使用 clean 样本和 EICAR 测试样本，预期输出 `ClamAV 1.5.4 real-engine validation passed: clean + EICAR rejected`。EICAR 是标准无害测试字符串，不是真实恶意样本。

协议依据：[ClamD Protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html)。
