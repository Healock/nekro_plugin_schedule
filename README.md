# NekroAgent 作息调度器

版本：`1.0.7`

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
- 同步 OneBot 在线状态，并通过全局巡检持续更新休眠剩余度。
- 在 Agent 上下文中提供当前状态、保护期和处理建议。
- 通过手动命令唤醒或进入休眠。
- 进入新的活跃时段后，自动解除此前的休眠状态。
- 进程重启或插件热重载后，会根据持久化的暂停频道记录恢复休眠前由插件切换的频道状态。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `weekday_low_activity` | `10:00-17:00` | 工作日低活跃时段 |
| `weekday_active` | `10:00-21:30` | 工作日活跃时段 |
| `weekend_active` | `08:00-23:00` | 周末活跃时段 |
| `patrol_interval` | `60` | 全局巡检间隔，单位为秒 |
| `status_sync_interval` | `60` | 在线状态和休眠剩余度刷新间隔，单位为秒 |
| `hint_low_activity` | 当前处于低活跃时段，回复可简短。 | 低活跃状态提示 |
| `hint_transition` | 接近休息时段，可在适当时调用 go_to_sleep。 | 休息状态提示 |

## 命令与沙盒方法

- `wake_up`：高级管理命令，清除当日休眠标记并唤醒系统。OneBot 用户需要具备高级命令权限；不要求加入全局超级用户列表。
- `go_to_sleep`：在允许的临界状态且保护期结束后进入休眠。
- `adjust_sleep_time`：延后指定分钟数后再进入休眠。
- `chat_schedule_prompt`：向 Agent 提供当前作息和保护期信息。

## 在线状态与休眠剩余度

插件使用 NapCat 的 `set_online_status` 接口表达作息状态：

- `NORMAL`：正常在线扩展状态，并发送当前休眠剩余度。
- `LOW_ACT`：忙碌状态。
- `TRANSITION`：熬夜中。
- `SILENT`：睡觉中。

`battery_status` 在本插件中不是设备真实电量，而是面向用户的休眠剩余度：活跃时段开始时接近 `100`，随着预计休息时间临近逐步下降，进入过渡或休眠状态后为 `0`。该值用于让用户了解 Bot 距离休眠还有多久。

状态巡检按 `patrol_interval` 运行，只有达到 `status_sync_interval`、作息状态变化或执行强制命令时才调用 NapCat。实际刷新频率取决于两者中较慢的一个。

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
