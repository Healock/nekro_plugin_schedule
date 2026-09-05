from typing import Any

from nonebot.exception import AdapterException
from nekro_agent.api import core

from .state_model import ChatState


def get_status_payload(state: ChatState) -> dict[str, int]:
    """返回 OneBot ``set_online_status`` 所需字段。"""

    if state == ChatState.SILENT:
        return {"status": 10, "ext_status": 1016}
    if state == ChatState.TRANSITION:
        return {"status": 10, "ext_status": 1032}
    if state == ChatState.LOW_ACT:
        return {"status": 50, "ext_status": 0}
    return {"status": 10, "ext_status": 1000}


async def sync_online_status(state: ChatState, battery_status: int) -> bool:
    """同步 OneBot 状态；适配器不可用时返回 False。"""

    try:
        from nekro_agent.adapters.onebot_v11.core.bot import get_bot
    except ImportError:
        return False

    try:
        bot: Any = get_bot()
        await bot.call_api(
            "set_online_status",
            **get_status_payload(state),
            battery_status=battery_status,
        )
    except (AdapterException, RuntimeError, TypeError, ValueError) as exc:
        core.logger.warning(f"[在线状态] OneBot 同步失败：{exc}")
        return False
    return True
