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
    batch_count: int | None = None
    reason: str = ""
    confirmed: bool | None = None

    def __post_init__(self) -> None:
        if self.confirmed is None:
            object.__setattr__(self, "confirmed", self.available and self.success)


def _result_from_value(value: Any) -> DebounceInvalidationResult:
    if isinstance(value, bool):
        return DebounceInvalidationResult(available=True, success=value, reason="legacy_result")

    def read(name: str, default: Any) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    return DebounceInvalidationResult(
        available=bool(read("available", True)),
        success=bool(read("success", False)),
        batch_count=max(0, int(read("batch_count", 0) or 0)),
        reason=str(read("reason", "") or ""),
        confirmed=bool(read("confirmed", False)),
    )


async def invalidate_debounce_channel(chat_key: str) -> DebounceInvalidationResult:
    """调用已加载防抖插件的版本化频道失效能力。"""

    try:
        from nekro_agent.services.plugin.collector import plugin_collector

        debounce_plugin = plugin_collector.get_plugin_by_module_name(DEBOUNCE_MODULE_NAME)
    except (ImportError, AttributeError, RuntimeError) as exc:
        return DebounceInvalidationResult(
            available=False,
            success=False,
            confirmed=False,
            reason=f"registry_unavailable:{type(exc).__name__}",
        )

    if debounce_plugin is None:
        return DebounceInvalidationResult(
            available=False,
            success=False,
            confirmed=False,
            reason="plugin_not_loaded",
        )

    bridge = getattr(debounce_plugin, "debounce_bridge", None)
    method = getattr(bridge, "invalidate_channel", None)
    version = getattr(bridge, "version", None)
    if version != CAPABILITY_VERSION or not callable(method):
        return DebounceInvalidationResult(
            available=False,
            success=False,
            confirmed=False,
            reason="capability_unavailable",
        )

    try:
        result = method(chat_key, "schedule_channel_switch")
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        return DebounceInvalidationResult(
            available=True,
            success=False,
            confirmed=False,
            reason=f"invalidation_failed:{type(exc).__name__}",
        )
    try:
        return _result_from_value(result)
    except (TypeError, ValueError, AttributeError) as exc:
        return DebounceInvalidationResult(
            available=True,
            success=False,
            confirmed=False,
            reason=f"invalid_result:{type(exc).__name__}",
        )
