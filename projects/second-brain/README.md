# 第二大脑：QQ 私人助理

QQ 转发通知和课件 → 保存原文与文件 → 自动提取任务 → 明确设置手机提醒 → 完成后取消剩余提醒。

**2026-11-04：现有 Windows 电脑上的第一条测试闭环已通过。当前为个人试用版，需 AstrBot 持续运行。下载代码不会自动完成安装与账号配置。**

| 你想做什么 | 入口 |
| --- | --- |
| 日常操作与故障处理 | [使用指南](USER_GUIDE.md) |
| 查看能做、不能做和数据去向 | [能力边界](BOUNDARIES.md) |
| 查看当前状态和下一步 | [迭代计划](ROADMAP.md) |
| 查看真实验证结果 | [实测记录](VALIDATION.md) |
| 继续开发与交接 | [维护说明](MAINTENANCE.md) |
| 查看变更历史 | [迭代记录](CHANGELOG.md) |
| 阅读长期需求 | [需求与方案](QQ_ASSISTANT_PLAN.md) |
| 在 Windows 检查部署 | [本机任务](WINDOWS_LOCAL_TASK.md)、[技术说明](windows/README.md) |

## 现在怎么用

1. 保持电脑联网、不休眠，AstrBot 运行，iPhone Bark 通知开启。
2. 向已绑定的机器人私聊转发文字通知，核对返回的任务编号、标题和截止时间。
3. 用 `提醒 任务编号 具体北京时间` 设置提醒；保存任务不会自动安排提醒。
4. 做完后发送 `完成 任务编号`，等待回执。
5. 附件下载成功后保留文件编号，需要原件时发送 `取回 文件编号`。

完整示例见[使用指南](USER_GUIDE.md)。目前不需要手动复制 JSON。

## 代码结构

- `astrbot_plugin_secondbrain_probe/`：当前 QQ 收件、归档、Codex 提取、任务和通知插件。
- `windows/`：安装校验助手与独立 Codex/Bark 测试工具。
- `test_qq_intake.py`、`test_tasks.py`：收件和队列测试。
- `brain.py`、`start.cmd`：保留的[手动桌面原型](LEGACY_LOCAL_INBOX.md)，与 QQ 助理数据不互通。

代码和脱敏文档在 GitHub；原文、课件、账号配置、设备密钥和运行数据库留在本机。GitHub 不负责运行机器人。
