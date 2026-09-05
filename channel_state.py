"""频道 ACTIVE/OBSERVE 状态切换与兼容存储。"""

import json
from collections.abc import Iterable
from typing import Any

from nekro_agent.api import core
from nekro_agent.models.db_chat_channel import DBChatChannel, ChannelStatus
from tortoise.exceptions import BaseORMException

from . import plugin
from .state_model import SLEEP_PAUSED_CHANNELS_KEY


def _decode_chat_keys(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, Iterable) or isinstance(value, (bytes, str, dict)):
        return []
    return [item for item in value if isinstance(item, str) and item]


async def pause_active_channels() -> bool:
    """将 ACTIVE 频道切换为 OBSERVE；部分失败时回滚已变更频道。"""

    try:
        channels = await DBChatChannel.all()
    except BaseORMException as exc:
        core.logger.error(f"[频道接管] 查询频道失败：{exc}")
        return False

    active_channels = [channel for channel in channels if channel.channel_status == ChannelStatus.ACTIVE]
    changed_channels: list[DBChatChannel] = []
    for channel in active_channels:
        try:
            await channel.set_channel_status(ChannelStatus.OBSERVE)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 暂停频道失败 chat_key={channel.chat_key}：{exc}")
        else:
            changed_channels.append(channel)

    if len(changed_channels) != len(active_channels):
        await _restore_channels(changed_channels, ChannelStatus.ACTIVE)
        return False

    active_keys = [channel.chat_key for channel in active_channels]
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
        return False
    core.logger.info(f"[频道接管] 休眠时暂停 {len(active_keys)} 个频道")
    return True


async def resume_paused_channels() -> bool:
    """恢复休眠前由插件切换的频道；部分失败时回滚已恢复频道。"""

    try:
        value = await plugin.store.get(
            chat_key="GLOBAL",
            user_key="",
            store_key=SLEEP_PAUSED_CHANNELS_KEY,
        )
    except BaseORMException as exc:
        core.logger.error(f"[频道接管] 读取暂停频道失败：{exc}")
        return False

    paused_keys = _decode_chat_keys(value)
    if not paused_keys:
        return True

    changed_channels: list[DBChatChannel] = []
    failed = False
    for chat_key in paused_keys:
        try:
            channel = await DBChatChannel.get_channel(chat_key=chat_key)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 查找暂停频道失败 chat_key={chat_key}：{exc}")
            failed = True
            continue
        if channel.channel_status != ChannelStatus.OBSERVE:
            continue
        try:
            await channel.set_channel_status(ChannelStatus.ACTIVE)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 恢复频道失败 chat_key={chat_key}：{exc}")
            failed = True
        else:
            changed_channels.append(channel)

    if failed:
        await _restore_channels(changed_channels, ChannelStatus.OBSERVE)
        return False

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
        return False
    core.logger.info(f"[频道接管] 唤醒时恢复 {len(changed_channels)} 个频道")
    return True


async def _restore_channels(channels: list[DBChatChannel], status: ChannelStatus) -> None:
    for channel in reversed(channels):
        try:
            await channel.set_channel_status(status)
        except (BaseORMException, ValueError, RuntimeError, AttributeError) as exc:
            core.logger.error(f"[频道接管] 补偿频道失败 chat_key={channel.chat_key}：{exc}")
