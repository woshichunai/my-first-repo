# Windows 本地试运行

选择已确定：使用可持续开机的 Windows 电脑；先测试现有资源，再决定新增预算。本阶段不购买服务器、不充值模型API。

这不是已经完成的QQ机器人。安装助手只准备并启动官方 AstrBot 安装包；接下来需要用户本人扫码登录，并由本机执行端继续接通AI处理和手机推送。

## 推荐入口

将上一级 [WINDOWS_LOCAL_TASK.md](../WINDOWS_LOCAL_TASK.md) 交给能执行本机命令的 Codex。它应先检查已有安装，保留现有配置，避免重复安装。

## 安装助手

`setup-astrbot.ps1` 支持 Windows AMD64/ARM64，下载官方 `v4.29.4` 安装包并验证发布资产的 SHA256，再打开普通安装界面。不会静默设置QQ、开放公网端口或添加付费服务。下载失败时直接报错，不使用第三方镜像。若电脑已安装AstrBot，可跳过。

由本机执行端在当前目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-astrbot.ps1
```

这里的 ExecutionPolicy 参数只影响该次 PowerShell 进程，不修改系统长期策略。电脑若有组织管理策略，应交由本机执行端按策略处理。

只下载、不启动安装界面：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-astrbot.ps1 -DownloadOnly
```

安装包保存在 `%LOCALAPPDATA%\SecondBrain\installers`。程序不会读取聊天、账号凭据、浏览器Cookie或现有数据目录。

## 来源与核查边界

- [官方桌面客户端说明](https://docs.astrbot.app/deploy/astrbot/desktop.html)
- [固定版本发布页](https://github.com/AstrBotDevs/AstrBot-desktop/releases/tag/v4.29.4)
- AMD64 SHA256：`7c65c03a9d6ed838a4f3ece11f7a88e44a81d0cfcb92094d1ebe14941938e1a6`
- ARM64 SHA256：`1da76d3fdaa980e57e89b32f9c532424707bb5cbbfda5b0ab571399b8fb781d3`

2026-11-03 已核对发布资产、URL和摘要；脚本尚未在 Windows 执行。此脚本既不代表软件安全审计，也不代表安装已完成。
