"""兼容 shim: 把对 engine.py 的 import 转发到 engine/ 子包。

历史: 原来 ScreeningEngine 全部实现在 engine.py (单文件 1386 行)。
重构后拆到 engine/ 子包,screening/search/detail/kline/cache 5 个 mixin。
但本文件作为兼容层保留,确保旧代码 `from engine import ScreeningEngine` 仍能工作。
"""
from engine import *  # noqa: F401,F403
from engine import ScreeningEngine  # noqa: F401  显式 re-export

__all__ = ['ScreeningEngine']
