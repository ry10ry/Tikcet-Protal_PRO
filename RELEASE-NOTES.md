# PROD v0.1 — 14 October 2026

首个完整、可独立部署的 PROD 版本。业务代码基于 UAT 提交 `ccb8c46`，补齐原始完整包中的 app/__init__.py、基础测试及证书工具。没有导入业务数据。

包含 Fault Ticket、CR、SR、统一通知页、月报导出、可配置 CR 审批流程、Outlook 邮件草稿、附件及截图、管理员管理、WAHA 新 Fault 通知、Warning/Error 日志、周备份与一年离线归档。

PROD 配套改动：独立 Compose 项目/外部卷、首次安装与断点续装脚本、随机数据库密码、新管理员、新 CA/服务器证书、默认禁用 WAHA、网页 PROD v0.1 标记、数据库就绪检查及 scheduler/proxy 启动依赖。UAT 仓库和部署不受此版本更改。

验证：SQLite 33 项、独立 MySQL 测试库 33 项通过；全新 Docker/MySQL、非 root web、scheduler、Nginx HTTPS、受信任 CA、特殊字符密码登录、空业务数据及一个管理员验证通过。PowerShell 全部语法检查通过，首次安装配置和重复安装保护通过模拟 Docker 调用验证。云端 Docker 构建容器无法直接解析 PyPI，因此容器验证使用主机下载的相同 requirements 依赖轮子离线构建；发布 Dockerfile 保留标准在线 pip 安装，新电脑构建需联网。实际 Windows 交互、USB、防火墙及客户端证书信任需安装后确认。
