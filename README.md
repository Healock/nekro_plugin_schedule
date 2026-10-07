# NekroAgent 作息调度器

版本：`1.1.1`

> 根据配置的时间段调整 Agent 的在线状态，并在休眠时切换频道观察模式。

## 快速开始

将整个 `nekro_plugin_schedule` 目录复制到 NekroAgent 数据目录的插件工作区：

```text
DATA_DIR/plugins/workdir/nekro_plugin_schedule/
```

确认目录中包含 `__init__.py`，然后按照 NekroAgent 的插件加载流程启动。

## 插件结构

```text
nekro_plugin_schedule/
├── __init__.py         # 插件实例、配置与包导出
├── state_model.py      # 频道状态和运行时状态模型
├── schedule_calc.py    # 时间段解析与状态计算
├── channel_state.py    # 频道 ACTIVE/OBSERVE 状态管理
├── debounce_bridge.py   # 防抖插件频道失效能力桥接
├── online_status.py    # OneBot 在线状态同步
├── schedule_service.py # 全局巡检服务
├── prompts.py          # 作息状态提示词
├── commands.py         # 命令与沙盒方法
├── lifecycle.py        # 初始化、巡检和清理
└── registration.py     # 模块注册
```

## 功能说明

- 按工作日和周末配置计算当前作息状态。
- 管理频道 `ACTIVE`、`OBSERVE` 等运行状态。
- 同步 OneBot 在线状态，并通过全局巡检持续更新。
- 在 Agent 上下文中提供当前状态、保护期和处理建议。
- 通过手动命令唤醒或进入休眠。
- 进入新的活跃时段后，自动解除此前的休眠状态。
- 休眠切换前通过已加载插件注册表调用防抖插件的频道失效能力；能力缺失时仍完成频道切换，并汇总记录未确认风险。

## 配置

`channel_resume_mode` 控制 NORMAL/LOW_ACT 时的频道恢复方式，默认值为 `managed`：只恢复插件在进入 SILENT 时记录的频道。设置为 `force` 时恢复所有非 DISABLED 频道，并清理已有的插件管理记录。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `weekday_low_activity` | `10:00-17:00` | 工作日低活跃时段 |
| `weekday_active` | `10:00-21:30` | 工作日活跃时段 |
| `weekend_active` | `08:00-23:00` | 周末活跃时段 |
| `patrol_interval` | `60` | 全局巡检间隔，单位为秒 |
| `hint_low_activity` | 当前处于低活跃时段，回复可简短。 | 低活跃状态提示 |
| `hint_transition` | 接近休息时段，可在适当时调用 go_to_sleep。 | 休息状态提示 |

## 命令与沙盒方法

- `wake_up`：高级管理命令，清除当日休眠标记并唤醒系统。OneBot 用户需要具备高级命令权限；不要求加入全局超级用户列表。
- `go_to_sleep`：在允许的临界状态且保护期结束后进入休眠。
- `adjust_sleep_time`：延后指定分钟数后再进入休眠。
- `chat_schedule_prompt`：向 Agent 提供当前作息和保护期信息。

## 开发

时间段解析和目标状态计算位于 `schedule_calc.py`，可以独立进行单元测试：

```powershell
python -m unittest test_schedule_calc.py
```

也可以执行插件目录下的 Python 语法检查：

```powershell
python -m py_compile *.py
```

完整行为需要真实的 NekroAgent、OneBot V11、频道数据库和在线状态接口环境验证。

## 相关资源

- [NekroAgent 官方文档](https://doc.nekro.ai/)
- [插件开发快速上手](https://doc.nekro.ai/docs/04_plugin_dev/01_quick_start.html)
- [Nekro 插件模板](https://github.com/KroMiose/nekro-plugin-template)

## 许可证

本项目当前未单独声明许可证。
