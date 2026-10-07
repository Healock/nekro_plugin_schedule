"""频道 ACTIVE/OBSERVE 状态切换与兼容存储。"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from nekro_agent.api import core
from nekro_agent.models.db_chat_channel import DBChatChannel, ChannelStatus
from tortoise.exceptions import BaseORMException

from . import plugin
from .debounce_bridge import DebounceInvalidationResult, invalidate_debounce_channel
from .state_model import SLEEP_PAUSED_CHANNELS_KEY


@dataclass(frozen=True)
class ChannelSwitchResult:
    success: bool
    debounce_confirmed: bool = True
    changed_keys: tuple[str, ...] = ()
    failed_keys: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.success


def _decode_chat_keys(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, Iterable) or isinstance(value, (bytes, str, dict)):
        return []
    return [item for item in value if isinstance(item, str) and item]


async def pause_active_channels() -> ChannelSwitchResult:
    """将 ACTIVE 频道切换为 OBSERVE；部分失败时回滚已变更频道。"""

    try:
        channels = await DBChatChannel.all()
        active_channels = [channel for channel in channels if channel.channel_status == ChannelStatus.ACTIVE]
    except (BaseORMException, RuntimeError, AttributeError) as exc:
        core.logger.error(f"[频道接管] 查询频道失败：{exc}")
        return ChannelSwitchResult(False)

    changed_channels: list[DBChatChannel] = []
    failed_keys: list[str] = []
    debounce_confirmed = True
    for channel in active_channels:
        try:
            is_active = channel.channel_status == ChannelStatus.ACTIVE
        except (RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 读取频道状态失败 chat_key={channel.chat_key}：{exc}")
            failed_keys.append(channel.chat_key)
            continue
        if not is_active:
            continue
        invalidation = await invalidate_debounce_channel(channel.chat_key)
        if isinstance(invalidation, bool):
            invalidation = DebounceInvalidationResult(True, invalidation)
        if not invalidation.success:
            debounce_confirmed = False
        else:
            debounce_confirmed = debounce_confirmed and bool(invalidation.confirmed)
        try:
            is_active = channel.channel_status == ChannelStatus.ACTIVE
        except (RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 读取频道状态失败 chat_key={channel.chat_key}：{exc}")
            failed_keys.append(channel.chat_key)
            continue
        if not is_active:
            continue
        try:
            await channel.set_channel_status(ChannelStatus.OBSERVE)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 暂停频道失败 chat_key={channel.chat_key}：{exc}")
            failed_keys.append(channel.chat_key)
        else:
            changed_channels.append(channel)

    if failed_keys:
        await _restore_channels(changed_channels, ChannelStatus.ACTIVE)
        return ChannelSwitchResult(False, debounce_confirmed, (), tuple(failed_keys))

    active_keys = [channel.chat_key for channel in changed_channels]
    if not active_keys:
        return ChannelSwitchResult(True)
    try:
        await plugin.store.set(
            chat_key="GLOBAL",
            user_key="",
            store_key=SLEEP_PAUSED_CHANNELS_KEY,
            value=json.dumps(active_keys, ensure_ascii=False),
        )
    except BaseORMException as exc:
        core.logger.error(f"[频道接管] 保存暂停频道失败：{exc}")
        await _restore_channels(changed_channels, ChannelStatus.ACTIVE)
        return ChannelSwitchResult(False, debounce_confirmed, (), tuple(active_keys))
    core.logger.info(f"[频道接管] 休眠时暂停 {len(active_keys)} 个频道")
    if not debounce_confirmed:
        core.logger.warning("[频道接管] 频道已切换，但部分防抖批次失效未确认")
    return ChannelSwitchResult(True, debounce_confirmed, tuple(active_keys))


async def resume_paused_channels(mode: str = "managed") -> ChannelSwitchResult:
    """恢复频道；managed 只恢复记录，force 恢复所有非 DISABLED 频道。"""

    if mode not in {"managed", "force"}:
        core.logger.warning(f"[频道接管] 未知恢复模式 {mode}，使用 managed")
        mode = "managed"

    try:
        value = await plugin.store.get(
            chat_key="GLOBAL",
            user_key="",
            store_key=SLEEP_PAUSED_CHANNELS_KEY,
        )
    except BaseORMException as exc:
        core.logger.error(f"[频道接管] 读取暂停频道失败：{exc}")
        return ChannelSwitchResult(False)

    paused_keys = _decode_chat_keys(value)
    if mode == "force":
        try:
            channels = await DBChatChannel.all()
        except (BaseORMException, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 查询待恢复频道失败：{exc}")
            return ChannelSwitchResult(False)
        disabled = getattr(ChannelStatus, "DISABLED", None)
        candidates = [channel for channel in channels if channel.channel_status != disabled]
    else:
        if not paused_keys:
            return ChannelSwitchResult(True)
        candidates = []
        for chat_key in paused_keys:
            try:
                channel = await DBChatChannel.get_channel(chat_key=chat_key)
            except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
                core.logger.error(f"[频道接管] 查找暂停频道失败 chat_key={chat_key}：{exc}")
                return ChannelSwitchResult(False, True, (), (chat_key,))
            if channel is not None:
                candidates.append(channel)

    changed_channels: list[DBChatChannel] = []
    failed_keys: list[str] = []
    for channel in candidates:
        chat_key = channel.chat_key
        if channel.channel_status == getattr(ChannelStatus, "DISABLED", object()):
            continue
        try:
            is_observe = channel.channel_status == ChannelStatus.OBSERVE
        except (RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 读取频道状态失败 chat_key={chat_key}：{exc}")
            failed_keys.append(chat_key)
            continue
        if not is_observe:
            continue
        try:
            await channel.set_channel_status(ChannelStatus.ACTIVE)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 恢复频道失败 chat_key={chat_key}：{exc}")
            failed_keys.append(chat_key)
        else:
            changed_channels.append(channel)

    if failed_keys:
        await _restore_channels(changed_channels, ChannelStatus.OBSERVE)
        return ChannelSwitchResult(False, True, (), tuple(failed_keys))

    try:
        await plugin.store.set(
            chat_key="GLOBAL",
            user_key="",
            store_key=SLEEP_PAUSED_CHANNELS_KEY,
            value="[]",
        )
    except BaseORMException as exc:
        core.logger.error(f"[频道接管] 清理暂停频道记录失败：{exc}")
        await _restore_channels(changed_channels, ChannelStatus.OBSERVE)
        return ChannelSwitchResult(False, True, (), tuple(paused_keys))
    core.logger.info(f"[频道接管] 唤醒时恢复 {len(changed_channels)} 个频道（模式：{mode}）")
    return ChannelSwitchResult(True, True, tuple(channel.chat_key for channel in changed_channels))


async def _restore_channels(channels: list[DBChatChannel], status: ChannelStatus) -> None:
    for channel in reversed(channels):
        try:
            await channel.set_channel_status(status)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 补偿频道失败 chat_key={channel.chat_key}：{exc}")
