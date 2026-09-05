"""根据作息时间调整 OneBot 在线状态与频道观察模式。"""

from pydantic import Field

from nekro_agent.api.plugin import ConfigBase, NekroPlugin

plugin = NekroPlugin(
    name="作息调度器",
    module_name="nekro_plugin_schedule",
    description="根据时间段调整在线状态，并在休眠时切换频道观察模式。",
    version="1.0.2",
    author="Healock",
    url="https://github.com/Healock/nekro_plugin_schedule",
)


@plugin.mount_config()
class ChatScheduleConfig(ConfigBase):
    weekday_low_activity: str = Field(default="10:00-17:00", title="工作日低活跃时段")
    weekday_active: str = Field(default="10:00-21:30", title="工作日活跃时段")
    weekend_active: str = Field(default="08:00-23:00", title="周末活跃时段")
    patrol_interval: int = Field(default=60, title="全局巡检间隔（秒）")
    hint_low_activity: str = Field(default="当前处于低活跃时段，回复可简短。", title="提示词：低活跃状态")
    hint_transition: str = Field(default="接近休息时段，可在适当时调用 go_to_sleep。", title="提示词：休息状态")


config = plugin.get_config(ChatScheduleConfig)

# 包根直接导出兼容名称。
from .channel_state import pause_active_channels, resume_paused_channels  # noqa: E402
from .commands import adjust_sleep_time, go_to_sleep, wake_up  # noqa: E402
from .lifecycle import clean_up, init_behavior_system  # noqa: E402
from .online_status import get_status_payload  # noqa: E402
from .prompts import inject_prompt  # noqa: E402
from .schedule_calc import ScheduleDecision, _is_in_range, calculate_schedule, is_in_range, parse_time_range  # noqa: E402
from .schedule_service import run_global_patrol, runtime_status, update_global_physical_status  # noqa: E402
from .state_model import ChatState, RuntimeStatus  # noqa: E402

__all__ = [
    "ChatScheduleConfig",
    "ChatState",
    "RuntimeStatus",
    "ScheduleDecision",
    "calculate_schedule",
    "clean_up",
    "config",
    "adjust_sleep_time",
    "go_to_sleep",
    "get_status_payload",
    "init_behavior_system",
    "inject_prompt",
    "is_in_range",
    "parse_time_range",
    "patrol_task",
    "plugin",
    "runtime_status",
    "update_global_physical_status",
    "wake_up",
]


def __getattr__(name: str) -> object:
    if name == "patrol_task":
        from . import lifecycle

        return lifecycle.patrol_task
    raise AttributeError(name)


# 注册模块放在包根加载流程末尾，保留插件收集顺序。
from . import registration as _registration  # noqa: E402,F401
