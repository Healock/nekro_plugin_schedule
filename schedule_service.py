import asyncio
from datetime import datetime

from nekro_agent.api import core

from . import config, plugin
from .channel_state import pause_active_channels, resume_paused_channels
from .online_status import sync_online_status
from .schedule_calc import calculate_schedule
from .state_model import FORCE_AWAKE_DATE_KEY, LAST_SLEEP_DATE_KEY, ChatState, RuntimeStatus

runtime_status = RuntimeStatus()


async def update_global_physical_status(forced_state: ChatState | str | None = None) -> bool:
    """计算并同步全局作息状态。"""

    try:
        from nekro_agent.adapters.onebot_v11.core.bot import get_bot
    except ImportError:
        return False
    if get_bot is None:
        return False

    now = datetime.now()
    persisted_sleep_date = await plugin.store.get(
        chat_key="GLOBAL",
        user_key="",
        store_key=LAST_SLEEP_DATE_KEY,
    )
    force_awake_date = await plugin.store.get(
        chat_key="GLOBAL",
        user_key="",
        store_key=FORCE_AWAKE_DATE_KEY,
    )
    decision = calculate_schedule(
        now=now,
        config=config,
        current_state=runtime_status.current_state,
        persisted_sleep_date=persisted_sleep_date,
        force_awake_date=force_awake_date,
        forced_state=forced_state,
    )

    previous_state = runtime_status.current_state
    should_sync = (
        decision.target_state != previous_state
        or now.timestamp() - runtime_status.last_sync_ts > 300
        or forced_state is not None
    )
    if not should_sync:
        return True

    if not await sync_online_status(decision.target_state, decision.battery_status):
        return False

    channels_ok = True
    if decision.target_state != previous_state:
        if decision.target_state == ChatState.SILENT:
            channels_ok = await pause_active_channels()
        elif previous_state == ChatState.SILENT:
            channels_ok = await resume_paused_channels()

    if not channels_ok:
        await sync_online_status(previous_state, runtime_status.battery_status)
        core.logger.error(f"[全局巡检] 状态已同步，但频道切换未完成：{previous_state} -> {decision.target_state}")
        return False

    runtime_status.current_state = decision.target_state
    runtime_status.battery_status = decision.battery_status
    runtime_status.last_sync_ts = now.timestamp()
    core.logger.info(
        f"[全局巡检] 状态：{decision.target_state}｜电量：{decision.battery_status}%｜算式：{decision.calculation}",
    )
    return True


async def run_global_patrol() -> None:
    """持续执行全局作息巡检。"""

    while True:
        try:
            await update_global_physical_status()
        except Exception as exc:
            core.logger.error(f"[全局巡检] 执行异常：{exc}")
        await asyncio.sleep(max(1, config.patrol_interval))
