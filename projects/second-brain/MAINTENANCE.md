# 维护与交接

## 统一来源

本仓库的 projects/second-brain 是代码、当前状态和使用文档的唯一迭代入口。Git 历史记录旧版本；本机私密目录保留实际部署状态与原始证据。GitHub 文档不能替代现场检查。

当前插件为 AstrBot 插件，不是 ChatGPT/ Codex Plugin Creator 托管插件。后者不是现有机器人运行或更新的必要组件。

## 继续任务时可以直接说

> 继续我的第二大脑项目。读取 woshichunai/my-first-repo 的 projects/second-brain/README.md、USER_GUIDE.md、BOUNDARIES.md、ROADMAP.md 和 MAINTENANCE.md。先核对 Windows 本机部署与 Git 状态，简述已完成、未完成和本轮下一步，然后直接执行。不要重复问已记录的设备与预算，不新增付费服务，不把代码和方案当作已部署。不能读取的文件要明确说明。保留本机私密数据，不上传课件、原文和凭据。

## 每轮更新流程

1. 检查远端和本地改动，保留未提交工作，在隔离分支实施。
2. 从 ROADMAP 选一个可验收项，先实现，再做适当测试与本机实测。
3. 记录失败和限制；只有真实达到验收标准才更新状态。
4. 更新 USER_GUIDE、BOUNDARIES、ROADMAP、VALIDATION、CHANGELOG，保持相互一致。
5. 只提交程序和脱敏文档；检查无账号密钥、推送地址、聊天、课件、数据库、带令牌日志。
6. GitHub 更新与本机部署分别记录。替换已安装插件前保留原版本和配置，不整目录覆盖账号数据。

## 代码与运行数据

插件代码：astrbot_plugin_secondbrain_probe。已安装的插件目录为用户目录下 `.astrbot/data/plugins/astrbot_plugin_secondbrain_probe`，部署后需重新加载插件或重启 AstrBot。

默认运行数据为 `%LOCALAPPDATA%/SecondBrain`：qq-intake 保存收件与原件，tasks.sqlite3 保存任务提醒，bark-probe 保存当前用户加密的设备配置，SETUP_STATUS.md 与 END_TO_END_RESULT.json 保存本机证据。Codex Windows 应用环境可能将此逻辑目录映射到应用的 LocalCache；不要因普通文件管理器路径不同就创建第二套空数据。可用 SECOND_BRAIN_HOME 覆盖收件/任务根目录，Bark 配置当前仍使用默认路径。

不要直接打印 AstrBot 账号配置或 Codex auth.json。设备配置使用当前 Windows 用户加密，复制到另一台电脑不等于可以直接解密。QQ 助理一键备份恢复尚未实现；不要套用旧桌面原型的备份功能。

## 验证命令（维护人员）

在 projects/second-brain 目录：

```text
python -m unittest -v test_brain test_qq_intake test_tasks
python -m unittest discover -s windows -p test_bark_probe.py -v
```

第二条包含 Windows 当前用户加密测试，需在 Windows 执行。插件还需在实际 AstrBot SDK 环境验证加载和事件处理。自动测试不等于 QQ 或手机实测。运行独立模型探针会使用现有订阅额度；不要为了文档修改重复发起模型调用或手机推送。

## 发布与回退

公开仓库仅保存源代码和脱敏记录，不包含本机配置、数据或现成登录状态。代码提交的回退不会自动回退本机数据库；插件代码、数据库结构和运行配置需分别检查兼容性。当前没有自动发布与迁移流水线。
