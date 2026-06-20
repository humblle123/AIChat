"""engine 子包,提供选股引擎的核心类。

模块拆分:
  - base       ScreeningEngine 主类、通用工具方法
  - screening  screen()  选股主流程
  - search     search()  股票搜索
  - detail     get_stock_detail() + 详情页组装
  - kline      get_kline() + 周月重采样
  - cache      get_cached_template_results()  模板缓存读

注意: 父目录有个同名 `engine.py`,Python 优先选子包。
本 __init__.py 负责把 base + 各 mixin 拼成完整的 ScreeningEngine。
"""
from engine.base import ScreeningEngine as _Base
from engine.screening import ScreeningMixin
from engine.search import SearchMixin
from engine.detail import DetailMixin
from engine.kline import KLineMixin
from engine.cache import CacheMixin


class ScreeningEngine(ScreeningMixin, SearchMixin, DetailMixin, KLineMixin, CacheMixin, _Base):
    """组合后的最终 ScreeningEngine(给 routes.py 用)。"""


__all__ = ['ScreeningEngine']
