# 一年归档：C 盘暂存、外接硬盘离线保存

初始暂存目录：`<PROD 项目目录>\MOMCC_Archive`。
Docker 始终挂载这个本地目录。外接硬盘只在搬移时连接，平时可拔掉，不需要修改 Docker 挂载或重启 Portal。

## 安装或从上一版更新

按包内相同路径覆盖项目文件，不覆盖 `.env`、数据库、附件卷。在项目目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Initialize-Archive.ps1 -ConfigurePortal
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml up -d --build --force-recreate web scheduler
```

初始化会设置项目内 `MOMCC_Archive` 为本地暂存区，保留 `.momcc-archive-target`，备份 `.env.before-archive`，只修改归档设置。`ARCHIVE_PURGE_ENABLED=false` 保持不变。若上一版已设为外接路径，先把原归档完整复制回 C 盘暂存目录（包括标记），再执行以上命令；遇到重名内容不一致应先停下核对，不要直接覆盖。不要用空的新标记替换既有标记。

按 Ctrl+F5，进入 **Admin → One-year Archive** 可立即生成归档。自动任务每天新加坡时间 03:00 时段复制，最多 20 张单；错过时段可手动执行。生成暂存归档不清理线上附件，因此仅生成归档不会释放 C 盘空间。

## 哪些记录归档

- Fault Ticket：Closed / Cancelled，结束已满一年。
- CR：Closed，关闭已满一年。
- SR：Approved，批准已满一年。

按完成日期计算一年，不按单号日期；未完成或近期完成的单保留线上。包含全部内容、评论、审批记录、历史版本、截图、CR 完成证明和 SR 已移除的历史附件。归档后单据只读，原业务状态保留。

## 连接硬盘后搬移

在实际外接盘上创建专用文件夹，例如 `E:\MOMCC_Archive`。该路径必须已存在，并使用与 C 盘不同的盘符。然后在项目目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Move-ArchiveOffline.ps1 -Destination "E:\MOMCC_Archive"
```

请将 E: 换成实际盘符。**此命令明确包含清理操作**：

1. 将暂存区内完整单据复制到外接盘，保留原目录结构和标记。
2. 对外接副本逐个验证 manifest 文件大小和 SHA256；已有目标内容不符时停止，保留线上及暂存副本。
3. 重建外接盘总目录 `index.html` 和 `archive.csv`，保留以前批次记录。
4. Portal 再验证 C 盘暂存文件与本次校验回执一致，清理对应线上附件，登记外接存放路径，再清理这批 C 盘暂存归档。文字、历史、报表仍在数据库。
5. 显示完成后，安全弹出硬盘。

不会清理本次没有成功登记的其他单据。不要在脚本执行中拔掉硬盘；如果中断或报错，保留两边文件并重试，查看 Warning/Error 日志。脚本不会覆盖不同内容的归档；遇到上次中断留下的不完整目标目录，需要核对后移到旁边保留，再重试。清理成功后，请保持外接归档的另一份独立备份，避免唯一硬盘损坏后无法找回附件。

## 平时硬盘不连接

Portal 正常运行；可按原有权限查询单据文字、评论、审批记录和导出 Monthly Report。CSV 增加 Archive State / Archive Path：`copied` 为已暂存，`archived` 为旧版已清理但本地归档仍在，`offline` 为已搬到离线硬盘。

离线单据显示附件存放位置，访问附件或生成需要附件的邮件草稿时会提示离线归档。**重新插上硬盘不会自动把附件接回 Portal**。查询历史附件时，直接打开硬盘根目录的 `index.html`，按单号、标题、提交人、类型和日期查询；进入单据即可看内容、历史和附件，截图可显示，也可导出筛选 CSV。无需 Portal、数据库或互联网。文件夹可以复制到另一台电脑查看。

## 验证、备份和空间

随时可单独检查外接归档：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-Archive.ps1 -ArchivePath "E:\MOMCC_Archive"
```

保留 `.momcc-archive-target`，不要单独搬附件或改目录结构。同一项目的后续批次继续放同一外接归档目录。换盘时先复制整个既有外接目录到新盘并验证，再使用新路径搬后续批次；数据库会保留各批次登记时的路径。

现有周备份不自动包含外接归档；数据库和离线归档应分别备份。数据库恢复后，只要有匹配的完整外接归档，仍可独立离线查询。

删除 CR/SR 数据库 BLOB 后，MySQL 可内部复用空间，但 Windows/Docker VHDX 的占用不一定立即缩小；不会自动执行数据库重建或磁盘压缩。Fault 文件及 C 盘暂存副本清理后释放对应文件空间。归档复制预留 100 MiB，不会通过自动删除未归档业务数据来处理空间不足。

## 文件和验证说明

包内新增 `app/archive.py`、`app/static/archive.js`、三个 scripts 归档脚本及本说明；其余文件按同路径覆盖。保留原始完整安装 ZIP，包内没有 `.env`、数据库或业务附件。

SQLite/MySQL 集成测试覆盖三类单据搬移、校验失败保留、清理、离线下载提示、断开硬盘后的列表及报表。PowerShell 已在 Linux 通过语法和复制/校验/回执流程验证；该测试用本地 Portal helper 替代 Docker 调用，并移除 Linux 不适用的盘符检查。实际 Windows USB 设备弹出行为仍需部署时验证。云端浏览器禁止 file://，独立页面已通过静态页面验证。
