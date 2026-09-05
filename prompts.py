import time

from nekro_agent.api import core
from nekro_agent.api.schemas import AgentCtx

from . import config, plugin
from .schedule_service import runtime_status
from .state_model import ChatState


def _suggestion(state: ChatState) -> str:
    if state == ChatState.LOW_ACT:
        return config.hint_low_activity
    if state == ChatState.TRANSITION:
        return config.hint_transition
    if state == ChatState.SILENT:
        return "保持休眠，等待 wake_up。"
    return "按正常作息处理。"


def _state_label(state: ChatState) -> str:
    return {
        ChatState.NORMAL: "正常",
        ChatState.LOW_ACT: "低活跃",
        ChatState.TRANSITION: "临界",
        ChatState.SILENT: "休眠",
    }[state]


@plugin.mount_prompt_inject_method(name="chat_schedule_prompt")
async def inject_prompt(_ctx: AgentCtx) -> str:
    """注入当前作息、保护期和状态建议。"""

    try:
        state = runtime_status.current_state
        remaining = runtime_status.protection_until - time.time()
        protection = f"剩余 {int(remaining / 60)} 分钟" if remaining > 0 else "无"
        return f"【作息状态】当前：{_state_label(state)}；保护期：{protection}；建议：{_suggestion(state)}"
    except Exception as exc:
        core.logger.warning(f"[作息提示] 注入失败：{exc}")
        return ""
