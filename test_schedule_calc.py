import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


def _load_calculator():
    package_name = "_schedule_calc_tests"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).parent)]
    sys.modules[package_name] = package
    for module_name in ("state_model", "schedule_calc"):
        full_name = f"{package_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(
            full_name,
            Path(__file__).parent / f"{module_name}.py",
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载测试模块：{module_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.schedule_calc"], sys.modules[f"{package_name}.state_model"]


schedule_calc, state_model = _load_calculator()
ChatState = state_model.ChatState
CONFIG = SimpleNamespace(
    weekday_low_activity="10:00-17:00",
    weekday_active="10:00-21:30",
    weekend_active="08:00-23:00",
)


class ScheduleCalculationTests(unittest.TestCase):
    def test_midnight_stays_transition(self):
        decision = schedule_calc.calculate_schedule(
            datetime(2026, 9, 7, 0, 0), CONFIG, ChatState.NORMAL, None, None,
        )
        self.assertEqual(decision.computed_state, ChatState.TRANSITION)
        self.assertEqual(decision.target_state, ChatState.TRANSITION)

    def test_forced_awake_before_active_period(self):
        decision = schedule_calc.calculate_schedule(
            datetime(2026, 9, 7, 7, 0), CONFIG, ChatState.TRANSITION, None, "2026-09-07",
        )
        self.assertEqual(decision.target_state, ChatState.NORMAL)

    def test_explicit_sleep_survives_midnight(self):
        decision = schedule_calc.calculate_schedule(
            datetime(2026, 9, 8, 0, 0), CONFIG, ChatState.SILENT, "2026-09-07", None,
        )
        self.assertEqual(decision.computed_state, ChatState.TRANSITION)
        self.assertEqual(decision.target_state, ChatState.SILENT)

    def test_morning_recovers_from_transition(self):
        decision = schedule_calc.calculate_schedule(
            datetime(2026, 9, 7, 10, 0), CONFIG, ChatState.TRANSITION, None, None,
        )
        self.assertEqual(decision.target_state, ChatState.LOW_ACT)

    def test_explicit_sleep_is_silent(self):
        now = datetime(2026, 9, 7, 12, 0)
        forced = schedule_calc.calculate_schedule(now, CONFIG, ChatState.NORMAL, None, None, ChatState.SILENT)
        persisted = schedule_calc.calculate_schedule(now, CONFIG, ChatState.NORMAL, "2026-09-07", None)
        self.assertEqual(forced.target_state, ChatState.SILENT)
        self.assertEqual(persisted.target_state, ChatState.SILENT)


if __name__ == "__main__":
    unittest.main()
