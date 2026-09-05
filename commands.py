import time
from datetime import datetime

from nekro_agent.api.plugin import CmdCtl, CommandExecutionContext, CommandPermission, CommandResponse, SandboxMethodType
from nekro_agent.api.schemas import AgentCtx

from . import plugin
from .schedule_service import runtime_status, update_global_physical_status
from .state_model import FORCE_AWAKE_DATE_KEY, LAST_SLEEP_DATE_KEY, ChatState


@plugin.mount_command(
    name="wake_up",
    description="手动唤醒",
    aliases=["wakeup", "强制唤醒"],
    permission=CommandPermission.SUPER_USER,
    category="行为控制",
)
async def wake_up(_context: CommandExecutionContext) -> CommandResponse:
    """清除当日休眠标记并唤醒。"""

    try:
        previous_sleep_date = await plugin.store.get(
            chat_key="GLOBAL", user_key="", store_key=LAST_SLEEP_DATE_KEY
        )
        previous_force_awake_date = await plugin.store.get(
            chat_key="GLOBAL", user_key="", store_key=FORCE_AWAKE_DATE_KEY
        )
        await plugin.store.set(chat_key="GLOBAL", user_key="", store_key=LAST_SLEEP_DATE_KEY, value="")
        await plugin.store.set(
            chat_key="GLOBAL",
            user_key="",
            store_key=FORCE_AWAKE_DATE_KEY,
            value=datetime.now().strftime("%Y-%m-%d"),
        )
        if not await update_global_physical_status(forced_state=ChatState.NORMAL):
            await plugin.store.set(
                chat_key="GLOBAL", user_key="", store_key=LAST_SLEEP_DATE_KEY, value=previous_sleep_date or ""
            )
            await plugin.store.set(
                chat_key="GLOBAL",
                user_key="",
                store_key=FORCE_AWAKE_DATE_KEY,
                value=previous_force_awake_date or "",
            )
            raise RuntimeError("在线状态或频道状态同步失败。")
    except Exception as exc:
        return CmdCtl.failed(f"唤醒未完成：{exc}")
    return CmdCtl.success("已唤醒并清除今日休眠状态。")


@plugin.mount_sandbox_method(
    SandboxMethodType.BEHAVIOR,
    name="go_to_sleep",
    description="进入休眠状态。需在 TRANSITION 状态且保护期结束后使用。",
)
async def go_to_sleep(_ctx: AgentCtx) -> str:
    if runtime_status.current_state != ChatState.TRANSITION:
        raise RuntimeError("当前不在可休眠状态。")
    remaining = runtime_status.protection_until - time.time()
    if remaining > 0:
        raise RuntimeError(f"当前处于保护期，还剩 {int(remaining / 60)} 分钟。")

    previous_sleep_date = await plugin.store.get(
        chat_key="GLOBAL", user_key="", store_key=LAST_SLEEP_DATE_KEY
    )
    await plugin.store.set(
        chat_key="GLOBAL",
        user_key="",
        store_key=LAST_SLEEP_DATE_KEY,
        value=datetime.now().strftime("%Y-%m-%d"),
    )
    if not await update_global_physical_status(forced_state=ChatState.SILENT):
        await plugin.store.set(
            chat_key="GLOBAL", user_key="", store_key=LAST_SLEEP_DATE_KEY, value=previous_sleep_date or ""
        )
        raise RuntimeError("在线状态或频道状态同步失败。")
    return "已进入休眠状态。"


@plugin.mount_sandbox_method(
    SandboxMethodType.BEHAVIOR,
    name="adjust_sleep_time",
    description="延后 go_to_sleep 指令指定分钟数。",
)
async def adjust_sleep_time(_ctx: AgentCtx, delay_minutes: int) -> str:
    if delay_minutes <= 0:
        raise ValueError("延后时长必须为正值。")
    runtime_status.protection_until = time.time() + delay_minutes * 60
    return f"休眠已延后 {delay_minutes} 分钟。"
