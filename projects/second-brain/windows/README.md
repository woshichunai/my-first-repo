# Windows 部署与验证工具

本机已有 AstrBot 4.29.4 和已配置的 QQ 试用插件；不要重复安装、重新配对或覆盖账号配置。新电脑下载代码不会自动获得这些配置。日常使用看 [USER_GUIDE.md](../USER_GUIDE.md)，当前状态看 [ROADMAP.md](../ROADMAP.md)。

## 工具与范围

| 文件 | 用途与限制 |
| --- | --- |
| setup-astrbot.ps1 | 官方固定版本安装包下载、SHA256 校验、普通安装界面；不配置 QQ、模型或手机 |
| probe-codex.py | 现有 ChatGPT 订阅登录的受监督合成样例验证；不创建真实任务，调用使用现有订阅额度 |
| bark_probe.py | 本机设备配置与独立三条通知测试；不是日常任务调度器 |
| test_bark_probe.py | Windows 加密、取消、恢复、漏发合并等本地测试 |

实际 QQ 助理位于上级 astrbot_plugin_secondbrain_probe，部署和私密数据位置见 [MAINTENANCE.md](../MAINTENANCE.md)。当前提醒队列在 AstrBot 插件内运行，不能通过仅运行旧版 start.cmd 启动。

## 安装助手

仅在未安装时使用，在本目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-astrbot.ps1
```

只下载和校验时加 `-DownloadOnly`。ExecutionPolicy 只影响该进程。支持 AMD64/ARM64，固定官方 v4.29.4，无第三方镜像；已在本机 PowerShell 与 Windows PowerShell 5.1 验证下载/校验。

下载目录为 `%LOCALAPPDATA%/SecondBrain/installers`。本机已安装并打开客户端，不代表该助手能自动完成所有账号配置。

## 本机运行要求

保持联网、不休眠，AstrBot 持续运行；管理端仅本机访问。不增加公网端口、服务器、订阅或另计费 API。Codex 登录由用户本人完成，不读取或打印 auth.json。Bark 地址只在本机配置，设备密钥按当前 Windows 用户加密。

本轮 QQ 与手机证据见 [VALIDATION.md](../VALIDATION.md)。开机启动与整机重启恢复尚未实测；安装校验不等于正式安全审计。

## 来源

- [AstrBot 桌面文档](https://docs.astrbot.app/deploy/astrbot/desktop.html)
- [固定版本发布页](https://github.com/AstrBotDevs/AstrBot-desktop/releases/tag/v4.29.4)
- [原始 Windows 执行要求](../WINDOWS_LOCAL_TASK.md)
