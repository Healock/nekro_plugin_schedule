from dataclasses import dataclass
from enum import StrEnum


class ChatState(StrEnum):
    NORMAL = "normal"
    LOW_ACT = "low_activity"
    TRANSITION = "transition"
    SILENT = "silent"


@dataclass
class RuntimeStatus:
    """进程内作息状态，不写入插件存储。"""

    current_state: ChatState = ChatState.NORMAL
    battery_status: int = 100
    last_sync_ts: float = 0.0
    protection_until: float = 0.0


SLEEP_PAUSED_CHANNELS_KEY = "sleep_paused_channels"
LAST_SLEEP_DATE_KEY = "last_sleep_date"
FORCE_AWAKE_DATE_KEY = "force_awake_date"
