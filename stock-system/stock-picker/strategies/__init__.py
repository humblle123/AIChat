"""策略模块"""
from strategies.base import BaseStrategy
from strategies.b1_strategy import B1Strategy
from strategies.s2_strategy import S2Strategy
from strategies.s3_strategy import S3Strategy
from strategies.kd1_strategy import KD1Strategy

# 策略注册表
STRATEGIES = {
    'b1': B1Strategy,
    's2': S2Strategy,
    's3': S3Strategy,
    'kd1': KD1Strategy,
}


def get_strategy(strategy_id: str, params: dict = None) -> BaseStrategy:
    """获取策略实例"""
    strategy_class = STRATEGIES.get(strategy_id)
    if strategy_class is None:
        raise ValueError(f"Unknown strategy: {strategy_id}")
    return strategy_class(params)


def list_strategies() -> list:
    """列出所有策略"""
    return [
        {
            'id': strategy_id,
            'name': cls().name,
            'description': cls().description,
        }
        for strategy_id, cls in STRATEGIES.items()
    ]


__all__ = [
    'BaseStrategy',
    'B1Strategy',
    'S2Strategy',
    'S3Strategy',
    'KD1Strategy',
    'STRATEGIES',
    'get_strategy',
    'list_strategies',
]
