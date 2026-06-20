"""策略基类"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd
from config import STRATEGY_DEFAULTS


class BaseStrategy(ABC):
    """选股策略基类"""
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化策略
        params: 可配置的参数，如 {'min_rps50': 90}
        """
        self.params = params or {}
        # 合并默认参数和自定义参数
        self._merge_params()
    
    def _merge_params(self):
        """合并默认参数"""
        defaults = STRATEGY_DEFAULTS.get(self.id, {})
        for key, value in defaults.items():
            if key not in self.params:
                self.params[key] = value
    
    @property
    @abstractmethod
    def id(self) -> str:
        """策略 ID"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass
    
    @property
    def description(self) -> str:
        """策略描述"""
        return ""
    
    @abstractmethod
    def screen(self, market_data: Dict) -> List[Dict]:
        """
        执行选股
        market_data 包含:
        - stock_list: DataFrame 股票列表
        - daily_data: Dict[code, DataFrame] 日线数据
        - rps_data: DataFrame RPS 数据
        """
        pass
    
    def format_signal(self, code: str, name: str, reason: str, metadata: Dict) -> Dict:
        """格式化选股信号"""
        return {
            'code': code,
            'name': name,
            'reason': reason,
            'metadata': metadata,
        }
