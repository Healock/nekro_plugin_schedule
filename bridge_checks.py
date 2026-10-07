"""无需 Nekro 运行时即可执行的桥接协议检查。"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path


def _load_bridge() -> types.ModuleType:
    module_name = "_schedule_debounce_bridge_check"
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name("debounce_bridge.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def _run(bridge: object):
    collector = types.SimpleNamespace(
        get_plugin_by_module_name=lambda _name: types.SimpleNamespace(debounce_bridge=bridge),
    )
    collector_module = types.ModuleType("nekro_agent.services.plugin.collector")
    collector_module.plugin_collector = collector
    for package_name in ("nekro_agent", "nekro_agent.services", "nekro_agent.services.plugin"):
        package = sys.modules.setdefault(package_name, types.ModuleType(package_name))
        package.__path__ = []
    sys.modules["nekro_agent.services.plugin.collector"] = collector_module
    return await _load_bridge().invalidate_debounce_channel("chat")


async def _confirmed(_chat_key: str, _reason: str):
    return {"available": True, "success": True, "confirmed": True, "batch_count": 0}


async def _failed(_chat_key: str, _reason: str):
    return {"available": True, "success": False, "confirmed": False, "reason": "failed"}


def main() -> None:
    confirmed = asyncio.run(_run(types.SimpleNamespace(version=1, invalidate_channel=_confirmed)))
    assert confirmed.confirmed is True
    assert confirmed.batch_count == 0

    failed = asyncio.run(_run(types.SimpleNamespace(version=1, invalidate_channel=_failed)))
    assert failed.available is True
    assert failed.success is False
    assert failed.confirmed is False


if __name__ == "__main__":
    main()
