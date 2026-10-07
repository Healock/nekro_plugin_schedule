"""通过已加载插件注册表调用防抖频道失效能力。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


DEBOUNCE_MODULE_NAME = "nekro_plugin_debounce"
CAPABILITY_VERSION = 1


@dataclass(frozen=True)
class DebounceInvalidationResult:
    available: bool
    success: bool
    confirmed: bool
    batch_count: int = 0
    reason: str = ""


def _result_from_value(value: Any) -> DebounceInvalidationResult:
    if isinstance(value, bool):
        return DebounceInvalidationResult(True, value, value, reason="legacy_result")

    def read(name: str, default: Any) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    return DebounceInvalidationResult(
        available=bool(read("available", True)),
        success=bool(read("success", False)),
        confirmed=bool(read("confirmed", False)),
        batch_count=max(0, int(read("batch_count", 0) or 0)),
        reason=str(read("reason", "") or ""),
    )


async def invalidate_debounce_channel(chat_key: str) -> DebounceInvalidationResult:
    """调用已加载防抖插件的版本化频道失效能力。"""

    try:
        from nekro_agent.services.plugin.collector import plugin_collector

        debounce_plugin = plugin_collector.get_plugin_by_module_name(DEBOUNCE_MODULE_NAME)
    except (ImportError, AttributeError, RuntimeError) as exc:
        return DebounceInvalidationResult(False, False, False, reason=f"registry_unavailable:{type(exc).__name__}")

    if debounce_plugin is None:
        return DebounceInvalidationResult(False, False, False, reason="plugin_not_loaded")

    bridge = getattr(debounce_plugin, "debounce_bridge", None)
    method = getattr(bridge, "invalidate_channel", None)
    version = getattr(bridge, "version", None)
    if version != CAPABILITY_VERSION or not callable(method):
        return DebounceInvalidationResult(False, False, False, reason="capability_unavailable")

    try:
        result = method(chat_key, "schedule_channel_switch")
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        return DebounceInvalidationResult(True, False, False, reason=f"invalidation_failed:{type(exc).__name__}")
    try:
        return _result_from_value(result)
    except (TypeError, ValueError, AttributeError) as exc:
        return DebounceInvalidationResult(
            available=True,
            success=False,
            confirmed=False,
            reason=f"invalid_result:{type(exc).__name__}",
        )
