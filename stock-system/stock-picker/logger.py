"""统一日志配置。

调用 `setup_logging()` 一次即可。后续模块用 `logger = logging.getLogger(__name__)`。
"""
import logging
import os
import sys


_initialized = False


def setup_logging(level: str = None) -> None:
    """初始化日志格式。多次调用幂等。"""
    global _initialized
    if _initialized:
        return

    level = level or os.environ.get('PICKER_LOG_LEVEL', 'INFO')
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)-7s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # 清掉 uvicorn / fastapi 等库可能加的 handler
    root.handlers.clear()
    root.addHandler(handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取 logger(自动 setup_logging)。"""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
