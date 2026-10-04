"""可选的防抖频道失效适配。"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Any

from nekro_agent.api import core


_INVALIDATION_METHODS = (
    "invalidate_channel",
    "invalidate_chat",
    "cancel_channel_pending",
)


@dataclass(frozen=True)
class DebounceInvalidationResult:
    available: bool
    success: bool
    batch_count: int | None = None
    reason: str = ""

    @property
    def confirmed(self) -> bool:
        return self.available and self.success


def _find_invalidation_method(module: Any) -> Any:
    runtime = getattr(module, "runtime", None)
    for owner in (runtime, module):
        if owner is None:
            continue
        for name in _INVALIDATION_METHODS:
            method = getattr(owner, name, None)
            if callable(method):
                return method
    return None


def _read_batch_count(result: Any) -> int | None:
    if isinstance(result, bool):
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        for key in ("batch_count", "generation_count", "canceled_count", "pending_count"):
            value = result.get(key)
            if isinstance(value, int):
                return value
    for key in ("batch_count", "generation_count", "canceled_count", "pending_count"):
        value = getattr(result, key, None)
        if isinstance(value, int):
            return value
    return None


def _read_success(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, dict) and "success" in result:
        return bool(result["success"])
    success = getattr(result, "success", None)
    return bool(success) if success is not None else True


async def invalidate_debounce_channel(chat_key: str) -> DebounceInvalidationResult:
    """调用已加载防抖插件的幂等频道失效入口。"""

    try:
        module = importlib.import_module("nekro_plugin_debounce")
    except (ImportError, RuntimeError, AttributeError) as exc:
        core.logger.warning(f"[频道接管] 防抖插件不可用，未确认失效 chat_key={chat_key}：{exc}")
        return DebounceInvalidationResult(False, True, reason="debounce_unavailable")

    method = _find_invalidation_method(module)
    if method is None:
        core.logger.warning(f"[频道接管] 防抖插件缺少频道失效入口，未确认失效 chat_key={chat_key}")
        return DebounceInvalidationResult(False, True, reason="invalidation_entry_missing")

    try:
        result = method(chat_key)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        core.logger.warning(f"[频道接管] 防抖频道失效失败 chat_key={chat_key}：{exc}")
        return DebounceInvalidationResult(True, False, reason=str(exc))

    success = _read_success(result)
    batch_count = _read_batch_count(result)
    if not success:
        core.logger.warning(
            f"[频道接管] 防抖频道失效返回失败 chat_key={chat_key} generation/批次数量={batch_count}",
        )
        return DebounceInvalidationResult(True, False, batch_count, reason="invalidation_returned_false")
    core.logger.info(
        f"[频道接管] 防抖频道失效完成 chat_key={chat_key} generation/批次数量={batch_count}",
    )
    return DebounceInvalidationResult(True, True, batch_count)
