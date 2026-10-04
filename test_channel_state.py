from __future__ import annotations

import asyncio
import importlib.util
from enum import Enum
import sys
import types
import unittest
from pathlib import Path


def _load_channel_state():
    package_name = "_schedule_channel_state_tests"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).parent)]  # type: ignore[attr-defined]
    package.plugin = types.SimpleNamespace(store=types.SimpleNamespace(set=_store_set, get=_store_get))
    sys.modules[package_name] = package

    core = types.ModuleType("nekro_agent.api.core")
    core.logger = types.SimpleNamespace(warning=lambda *_args: None, error=lambda *_args: None, info=lambda *_args: None)
    api = types.ModuleType("nekro_agent.api")
    api.core = core
    root = types.ModuleType("nekro_agent")
    root.__path__ = []  # type: ignore[attr-defined]
    db = types.ModuleType("nekro_agent.models.db_chat_channel")

    class ChannelStatus(str, Enum):
        ACTIVE = "active"
        OBSERVE = "observe"

    class DBChatChannel:
        channels = []

        @classmethod
        async def all(cls):
            return list(cls.channels)

    db.DBChatChannel = DBChatChannel
    db.ChannelStatus = ChannelStatus
    tortoise = types.ModuleType("tortoise")
    exceptions = types.ModuleType("tortoise.exceptions")

    class BaseORMException(Exception):
        pass

    exceptions.BaseORMException = BaseORMException
    tortoise.exceptions = exceptions
    state_model = types.ModuleType(f"{package_name}.state_model")
    state_model.SLEEP_PAUSED_CHANNELS_KEY = "sleep_paused_channels"
    sys.modules.update({
        "nekro_agent": root,
        "nekro_agent.api": api,
        "nekro_agent.api.core": core,
        "nekro_agent.models": types.ModuleType("nekro_agent.models"),
        "nekro_agent.models.db_chat_channel": db,
        "tortoise": tortoise,
        "tortoise.exceptions": exceptions,
        f"{package_name}.state_model": state_model,
    })
    spec = importlib.util.spec_from_file_location(f"{package_name}.channel_state", Path(__file__).parent / "channel_state.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, DBChatChannel, ChannelStatus


_STORE: dict[str, str] = {}


async def _store_set(**kwargs):
    _STORE[kwargs["store_key"]] = kwargs["value"]
    return 1


async def _store_get(**kwargs):
    return _STORE.get(kwargs["store_key"])


class ChannelStateTests(unittest.TestCase):
    def test_pause_calls_optional_debounce_invalidation_before_observe(self) -> None:
        async def run() -> None:
            module, db_channel, status = _load_channel_state()
            events: list[str] = []

            class Channel:
                chat_key = "chat"
                channel_status = status.ACTIVE

                async def set_channel_status(self, new_status):
                    events.append(f"status:{new_status}")
                    self.channel_status = new_status

            db_channel.channels[:] = [Channel()]
            debounce = types.ModuleType("nekro_plugin_debounce")

            async def invalidate(chat_key: str, reason: str):
                events.append(f"invalidate:{chat_key}:{reason}")

            debounce.invalidate_channel = invalidate
            sys.modules["nekro_plugin_debounce"] = debounce

            self.assertTrue(await module.pause_active_channels())
            self.assertEqual(events, ["invalidate:chat:schedule_observe", f"status:{status.OBSERVE}"])

        asyncio.run(run())

    def test_missing_debounce_plugin_does_not_block_invalidation_helper(self) -> None:
        async def run() -> None:
            module, _db_channel, _status = _load_channel_state()
            sys.modules.pop("nekro_plugin_debounce", None)
            await module._invalidate_debounce_channel("chat")

        asyncio.run(run())
