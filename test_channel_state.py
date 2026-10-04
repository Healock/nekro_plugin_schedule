import importlib.util
import sys
import types
import unittest
from enum import StrEnum
from pathlib import Path


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


class _Store:
    def __init__(self):
        self.values = {}
        self.set_calls = []

    async def get(self, **kwargs):
        return self.values.get(kwargs["store_key"])

    async def set(self, **kwargs):
        self.set_calls.append(kwargs)
        self.values[kwargs["store_key"]] = kwargs["value"]


class _Plugin:
    def __init__(self):
        self.store = _Store()


class _ChannelStatus(StrEnum):
    ACTIVE = "active"
    OBSERVE = "observe"


class _Channel:
    def __init__(self, chat_key, status, fail=False):
        self.chat_key = chat_key
        self.channel_status = status
        self.fail = fail
        self.status_history = []

    async def set_channel_status(self, status):
        self.status_history.append(status)
        if self.fail:
            raise ValueError("synthetic channel failure")
        self.channel_status = status


def _load_channel_state():
    package_name = "_channel_state_tests"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).parent)]
    package.plugin = _Plugin()
    sys.modules[package_name] = package

    core_module = types.ModuleType("nekro_agent.api.core")
    core_module.logger = _Logger()
    api_module = types.ModuleType("nekro_agent.api")
    api_module.core = core_module
    models_module = types.ModuleType("nekro_agent.models.db_chat_channel")
    models_module.ChannelStatus = _ChannelStatus

    class _DBChatChannel:
        channels = []

        @classmethod
        async def all(cls):
            return cls.channels

        @classmethod
        async def get_channel(cls, chat_key):
            for channel in cls.channels:
                if channel.chat_key == chat_key:
                    return channel
            raise ValueError(f"channel not found: {chat_key}")

    models_module.DBChatChannel = _DBChatChannel
    tortoise_module = types.ModuleType("tortoise")
    exceptions_module = types.ModuleType("tortoise.exceptions")

    class _BaseORMException(Exception):
        pass

    exceptions_module.BaseORMException = _BaseORMException
    tortoise_module.exceptions = exceptions_module
    stub_names = (
        "nekro_agent",
        "nekro_agent.api",
        "nekro_agent.api.core",
        "nekro_agent.models",
        "nekro_agent.models.db_chat_channel",
        "tortoise",
        "tortoise.exceptions",
    )
    previous_modules = {name: sys.modules.get(name) for name in stub_names}
    sys.modules.update(
        {
            "nekro_agent": types.ModuleType("nekro_agent"),
            "nekro_agent.api": api_module,
            "nekro_agent.api.core": core_module,
            "nekro_agent.models": types.ModuleType("nekro_agent.models"),
            "nekro_agent.models.db_chat_channel": models_module,
            "tortoise": tortoise_module,
            "tortoise.exceptions": exceptions_module,
        },
    )

    for module_name in ("debounce_bridge", "channel_state"):
        full_name = f"{package_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full_name, Path(__file__).parent / f"{module_name}.py")
        if spec is None or spec.loader is None:
            raise ImportError(full_name)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
    for name, previous in previous_modules.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return sys.modules[f"{package_name}.channel_state"], models_module.DBChatChannel, package.plugin


channel_state, DBChatChannel, plugin = _load_channel_state()
ChannelStatus = _ChannelStatus
DebounceInvalidationResult = sys.modules["_channel_state_tests.debounce_bridge"].DebounceInvalidationResult
debounce_bridge = sys.modules["_channel_state_tests.debounce_bridge"]


class ChannelStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        plugin.store.values.clear()
        plugin.store.set_calls.clear()

    async def test_pause_calls_invalidation_for_active_channels(self):
        first = _Channel("active-1", ChannelStatus.ACTIVE)
        second = _Channel("observe-1", ChannelStatus.OBSERVE)
        DBChatChannel.channels = [first, second]
        calls = []

        async def invalidate(chat_key):
            calls.append(chat_key)
            return DebounceInvalidationResult(True, True, 1)

        channel_state.invalidate_debounce_channel = invalidate
        result = await channel_state.pause_active_channels()
        self.assertTrue(result.success)
        self.assertEqual(calls, ["active-1"])
        self.assertEqual(first.channel_status, ChannelStatus.OBSERVE)

    async def test_missing_entry_keeps_legacy_switch_unconfirmed(self):
        channel = _Channel("active-1", ChannelStatus.ACTIVE)
        DBChatChannel.channels = [channel]

        async def missing(_chat_key):
            return DebounceInvalidationResult(False, True, reason="missing")

        channel_state.invalidate_debounce_channel = missing
        result = await channel_state.pause_active_channels()
        self.assertTrue(result.success)
        self.assertFalse(result.debounce_confirmed)
        self.assertEqual(channel.channel_status, ChannelStatus.OBSERVE)

    async def test_invalidation_failure_rolls_back(self):
        first = _Channel("active-1", ChannelStatus.ACTIVE)
        second = _Channel("active-2", ChannelStatus.ACTIVE)
        DBChatChannel.channels = [first, second]

        async def fail_second(chat_key):
            return DebounceInvalidationResult(True, chat_key != "active-2", 1, "synthetic")

        channel_state.invalidate_debounce_channel = fail_second
        result = await channel_state.pause_active_channels()
        self.assertFalse(result.success)
        self.assertEqual(first.channel_status, ChannelStatus.ACTIVE)
        self.assertEqual(plugin.store.set_calls, [])

    async def test_partial_channel_failure_does_not_persist(self):
        first = _Channel("active-1", ChannelStatus.ACTIVE)
        second = _Channel("active-2", ChannelStatus.ACTIVE, fail=True)
        DBChatChannel.channels = [first, second]
        channel_state.invalidate_debounce_channel = lambda _chat_key: _success()
        result = await channel_state.pause_active_channels()
        self.assertFalse(result.success)
        self.assertEqual(first.channel_status, ChannelStatus.ACTIVE)
        self.assertEqual(plugin.store.set_calls, [])

    async def test_resume_does_not_invalidate_old_batches_and_is_idempotent(self):
        channel = _Channel("active-1", ChannelStatus.OBSERVE)
        DBChatChannel.channels = [channel]
        plugin.store.values["sleep_paused_channels"] = '["active-1"]'
        calls = []

        async def unexpected(chat_key):
            calls.append(chat_key)
            return DebounceInvalidationResult(True, True)

        channel_state.invalidate_debounce_channel = unexpected
        first = await channel_state.resume_paused_channels()
        second = await channel_state.resume_paused_channels()
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(calls, [])
        self.assertEqual(channel.channel_status, ChannelStatus.ACTIVE)

    async def test_repeated_pause_preserves_persisted_keys(self):
        channel = _Channel("active-1", ChannelStatus.ACTIVE)
        DBChatChannel.channels = [channel]

        async def invalidate(_chat_key):
            return DebounceInvalidationResult(True, True, 1)

        channel_state.invalidate_debounce_channel = invalidate
        first = await channel_state.pause_active_channels()
        second = await channel_state.pause_active_channels()
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(plugin.store.values["sleep_paused_channels"], '["active-1"]')

    async def test_manual_observe_channel_is_not_recorded(self):
        channel = _Channel("active-1", ChannelStatus.ACTIVE)
        DBChatChannel.channels = [channel]

        async def user_observes(_chat_key):
            channel.channel_status = ChannelStatus.OBSERVE
            return DebounceInvalidationResult(True, True, 1)

        channel_state.invalidate_debounce_channel = user_observes
        result = await channel_state.pause_active_channels()
        self.assertTrue(result.success)
        self.assertEqual(plugin.store.set_calls, [])

    async def test_missing_debounce_plugin_is_optional(self):
        original_import = debounce_bridge.importlib.import_module

        def missing(_name):
            raise ImportError("synthetic missing plugin")

        debounce_bridge.importlib.import_module = missing
        try:
            result = await debounce_bridge.invalidate_debounce_channel("active-1")
        finally:
            debounce_bridge.importlib.import_module = original_import
        self.assertTrue(result.success)
        self.assertFalse(result.available)
        self.assertFalse(result.confirmed)


async def _success():
    return DebounceInvalidationResult(True, True, 0)


if __name__ == "__main__":
    unittest.main()
