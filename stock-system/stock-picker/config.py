"""配置文件"""
import os

# 数据库路径(可被 PICKER_DB_DIR 环境变量覆盖,方便测试时用临时 DB)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.environ.get('PICKER_DB_DIR') or os.path.join(BASE_DIR, 'data')
DATA_DIR = _DATA_DIR
DB_PATH = os.path.join(_DATA_DIR, 'stocks.db')

# 腾讯财经 API
TENCENT_API = {
    'quote': 'http://qt.gtimg.cn/q=',      # 实时行情
    'kline': 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get',  # K线数据
}

# 数据更新配置
UPDATE_CONFIG = {
    'trading_hours': {
        'morning': ('09:30', '11:30'),
        'afternoon': ('13:00', '15:00'),
    },
    'after_close': '20:00',  # 盘后更新时间
    'daily_screen': '20:10',  # 选股更新时间，确保在盘后更新之后执行
}

# 策略默认参数
STRATEGY_DEFAULTS = {
    'b1': {
        'j_threshold': 18,
        'min_rps50': 0,
        'min_rps120': 0,
        'min_rps250': 0,
    },
    's2': {
        'ma_period': 250,
        'new_high_days': 50,
        'min_rps50': 85,
        'min_above_ma_days': 2,
        'max_above_ma_days': 30,
    },
    's3': {
        'min_rps50': 90,
        'min_rps120': 93,
        'min_rps250': 95,
        'near_high_threshold': 0.85,
    },
    'kd1': {
        'min_rps': 95,
        'near_high_threshold': 0.6,
    },
}

# RPS 计算周期
RPS_PERIODS = [50, 120, 250]

# 排除规则统一使用 stock_basic.is_st 字段过滤，不再用关键字匹配
