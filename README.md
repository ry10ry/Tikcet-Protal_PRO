# MOMCC ServiceDesk — PROD v0.1

正式版完整源码，适用于一台新的 Windows 电脑。当前 UAT 继续使用原仓库 `Ticket-portal---v2`；本仓库 `Tikcet-Protal_PRO` 独立发布 PROD。此版本不包含 UAT 数据、账号、密码、附件、日志或证书。

## 新电脑首次安装

1. 安装 Docker Desktop，启用 WSL2 / Linux containers，启动并等待 Docker 就绪。安装 Git（可选）；构建镜像需要互联网。
2. 为电脑设置固定局域网 IPv4（或 DHCP 地址保留）。记录 `ipconfig` 中实际网卡的 IPv4；不要填 UAT IP、127.0.0.1 或 Docker 虚拟网卡地址。
3. 下载本仓库的 **main 分支最新 ZIP**（界面版本仍为 v0.1） 并解压到本地目录，例如 `C:\MOMCC-ServiceDesk-PROD`。也可用 Git：

```powershell
git clone --branch main https://github.com/ry10ry/Tikcet-Protal_PRO.git C:\MOMCC-ServiceDesk-PROD
cd C:\MOMCC-ServiceDesk-PROD
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-PROD.ps1
```

脚本会询问 PROD 电脑 IP、管理员 Email 和新密码（至少 12 字符，隐藏输入）。自动生成两套随机数据库密码，写入本机 `.env`，创建独立空卷、构建程序、生成新的 HTTPS 证书并启动。

**不要先手动复制 `.env.example` 为 `.env` 再执行 Setup。** Setup 为首次安装设计，发现已有 `.env` 或 PROD 卷会停止保护现有环境，不会重置或删除数据。`.env.example` 仅供参考。若首次安装中断，修复 Docker/网络后执行 `Resume-PROD.ps1`，保留生成的 `.env` 和卷。

## 首次访问

启动成功会显示 `https://<PROD电脑IP>`。将 **`ssl\certs\root-ca.cer`** 导入每台访问电脑的“受信任的根证书颁发机构”，然后访问并使用刚设置的管理员账号登录。不要分发任何 `.key` 文件。证书有效期一年；CA 有效期十年。改变服务器 IP 或证书到期前执行 `Generate-Cert.ps1 -PortalIP 新IP`，再运行 `Start-HTTPS.ps1`；不要删除原 CA。

如其他电脑无法访问：确认同一网络能够访问 PROD IP，并在 Windows 防火墙允许 TCP 443。可用管理员 PowerShell添加局域网规则：

```powershell
New-NetFirewallRule -DisplayName "MOMCC PROD HTTPS" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 -RemoteAddress LocalSubnet -Profile Private,Domain
```

防火墙规则取决于实际网络策略；安装程序不自动修改防火墙。8000 只绑定本机，MySQL 不开放宿主端口。

初次数据库只包含一个管理员和默认设置，没有演示用户、单据、审批或附件。在 Users 中新增正式用户；在 Admin 中设置分类、动作和 CR 审批流程。管理员密码以后在 Users 页面修改；改 `.env` 不会重置数据库内已有账号。

## 日常运行与升级

Docker Desktop 设置为登录 Windows 后启动；PROD 电脑需保持开机，关闭睡眠。容器设置自动重启；Windows 重启后仍需 Docker Desktop 启动。

```powershell
# 正常启动 / HTTPS 配置校验
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-HTTPS.ps1

# 状态及日志
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml ps
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml logs --tail 100 web scheduler proxy

# 下载经过 UAT 验证的新正式版本、备份后，重建程序
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml up -d --build --force-recreate web scheduler proxy
```

不要用新的包覆盖本机 `.env`、`ssl/certs`、`MOMCC_Archive`、`logs`；不要对已运行系统重新执行首次安装。先在 UAT 测试，再在本仓库发布新标签。GitHub 默认分支 main 包含已批准的最新更新；首版标签 v0.1 保留初次发布快照，不移动旧标签；界面及 `/api/health` 显示 PROD v0.1。`/api/health` 同时检查数据库连接。它不显示凭证或业务数据。

## 独立存储和备份

| 项目 | PROD 配置 |
|---|---|
| Compose 项目名 | `momcc-prod` |
| 数据库卷 | `momcc-prod_mysql_data`（external） |
| 附件卷 | `momcc-prod_attachments_data`（external） |
| 本地归档暂存 | 项目目录 `MOMCC_Archive` |
| Warning / Error 日志 | 项目目录 `logs` |
| HTTPS 证书 | 项目目录 `ssl/certs` |

External 卷不会被 Compose `down -v` 删除，但手动删除卷或 Docker Desktop 恢复出厂会丢数据。不要把 UAT 卷、数据库备份或证书导入这台全新 PROD。

可安装每周日凌晨 02:00 的周备份，保留最近八份成功备份（Windows 本地时间，建议设新加坡时区）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-WeeklyBackup.ps1 -BackupRoot "C:\Docker databackup\PROD"

# 立即做一次备份检查
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Backup-ServiceDesk.ps1 -BackupRoot "C:\Docker databackup\PROD"
```

任务名为 `MOMCC PROD Weekly Backup`，要求安装任务的 Windows 用户已登录且 Docker Desktop 正在运行。备份期间会短暂停止 web/scheduler。检查备份 SUCCESS.json；C 盘备份不能抵御整机损坏，应另存到另一设备。归档暂存区及外接离线归档不在周备份范围内，需独立备份，参见 [归档说明](ARCHIVING.md)。

归档默认每天 03:00 SGT 复制完成满一年的记录；平时只挂载 C 盘暂存目录。连接外接硬盘时执行 Move-ArchiveOffline.ps1，验证成功后才登记及清理，随后可拔盘。详见 ARCHIVING.md。

WhatsApp 默认关闭，避免误发到 UAT 群组。需要时按 WHATSAPP-WAHA.md 设置正式配置并重新创建 web/scheduler。

## 开发验证

运行环境 Python 3.12，依赖版本在 requirements.txt。测试额外需要 `pytest` 和 `httpx`；SQLite 是默认测试数据库，不能使用正式数据库运行测试。UAT 基线来源提交见 RELEASE-NOTES.md。云端已验证程序和容器流程；Windows 防火墙、证书信任和实际用户电脑连接需在安装后确认。
