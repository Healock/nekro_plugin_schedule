from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol

from .state_model import ChatState


class ScheduleConfigLike(Protocol):
    weekday_low_activity: str
    weekday_active: str
    weekend_active: str


@dataclass(frozen=True)
class ScheduleDecision:
    """隔离状态计算结果与外部副作用。"""

    computed_state: ChatState
    target_state: ChatState
    battery_status: int
    calculation: str


def parse_time_range(range_str: str) -> tuple[time, time] | None:
    """解析 ``HH:MM-HH:MM``，格式无效时返回空值。"""

    try:
        start_text, end_text = (part.strip() for part in range_str.split("-", maxsplit=1))
        return (
            datetime.strptime(start_text, "%H:%M").time(),
            datetime.strptime(end_text, "%H:%M").time(),
        )
    except (AttributeError, TypeError, ValueError):
        return None


def is_in_range(now: datetime, range_str: str) -> bool:
    parsed = parse_time_range(range_str)
    if parsed is None:
        return False
    start, end = parsed
    return start <= now.time() <= end


def _schedule_window(now: datetime, config: ScheduleConfigLike) -> tuple[time, time]:
    if now.weekday() >= 5:
        return parse_time_range(config.weekend_active) or (time(9, 0), time(22, 0))

    low = parse_time_range(config.weekday_low_activity)
    active = parse_time_range(config.weekday_active)
    if low is None or active is None:
        return time(9, 0), time(22, 0)
    return min(low[0], active[0]), max(low[1], active[1])


def calculate_schedule(
    now: datetime,
    config: ScheduleConfigLike,
    current_state: ChatState,
    persisted_sleep_date: str | None,
    force_awake_date: str | None,
    forced_state: ChatState | str | None = None,
) -> ScheduleDecision:
    """根据输入快照计算作息状态，不执行存储或外部调用。"""

    start_time, end_time = _schedule_window(now, config)
    start_dt = datetime.combine(now.date(), start_time)
    end_dt = datetime.combine(now.date(), end_time)
    today = now.strftime("%Y-%m-%d")

    if now < start_dt:
        if force_awake_date == today:
            computed_state, battery, calculation = ChatState.NORMAL, 100, f"强制早起（<{start_time:%H:%M}）"
        else:
            computed_state, battery, calculation = ChatState.TRANSITION, 0, f"活跃时段前（<{start_time:%H:%M}）"
    elif now >= end_dt:
        computed_state, battery, calculation = ChatState.TRANSITION, 0, f"活跃时段后（>{end_time:%H:%M}）"
    else:
        low_activity = now.weekday() < 5 and is_in_range(now, config.weekday_low_activity)
        computed_state = ChatState.LOW_ACT if low_activity else ChatState.NORMAL
        total_seconds = (end_dt - start_dt).total_seconds()
        elapsed_seconds = (now - start_dt).total_seconds()
        battery = int(max(0, min(100, (1.0 - elapsed_seconds / total_seconds) * 100))) if total_seconds > 0 else 100
        calculation = f"100 ×（1－{int(elapsed_seconds)}秒/{int(total_seconds)}秒）"

    if forced_state is not None:
        target_state = ChatState(forced_state)
    elif persisted_sleep_date == today:
        target_state = ChatState.SILENT
    elif current_state == ChatState.SILENT and computed_state == ChatState.TRANSITION:
        target_state = ChatState.SILENT
    elif computed_state == ChatState.TRANSITION:
        target_state = ChatState.TRANSITION
    else:
        target_state = computed_state

    return ScheduleDecision(computed_state, target_state, battery, calculation)


_is_in_range = is_in_range
