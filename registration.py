"""集中加载插件各职责模块，使包根保持稳定导出。"""

from . import channel_state as _channel_state  # noqa: F401
from . import commands as _commands  # noqa: F401
from . import lifecycle as _lifecycle  # noqa: F401
from . import prompts as _prompts  # noqa: F401

