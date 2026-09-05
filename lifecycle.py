import asyncio
from contextlib import suppress

from nekro_agent.api import core

from . import config, plugin
from .schedule_service import run_global_patrol

patrol_task: asyncio.Task[None] | None = None


@plugin.mount_init_method()
async def init_behavior_system() -> None:
    """启动全局作息巡检任务。"""

    global patrol_task
    if patrol_task and not patrol_task.done():
        return
    patrol_task = asyncio.create_task(run_global_patrol(), name="schedule-global-patrol")
    core.logger.info(f"[作息调度] 状态巡检已启动，间隔 {config.patrol_interval} 秒")


@plugin.mount_cleanup_method()
async def clean_up() -> None:
    """停止巡检任务并释放任务引用。"""

    global patrol_task
    if patrol_task is None:
        return
    patrol_task.cancel()
    with suppress(asyncio.CancelledError):
        await patrol_task
    patrol_task = None
