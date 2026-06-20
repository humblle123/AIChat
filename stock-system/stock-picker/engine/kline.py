"""KLineMixin: K 线 + 周月重采样。

优先从 stock_kline_cache 读盘后预计算结果,无缓存时才从 stock_daily 实时算。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

import numpy as np

from data.store import get_daily_data_df, get_rps_data, get_rps_history, get_kline_cache


class KLineMixin:
    """提供 `get_kline()`,支持日/周/月,优先走缓存。"""

    def get_kline(self, code: str, period: str = 'day') -> Optional[Dict]:
        period_key = str(period).lower()
        if period_key not in ('day', 'week', 'month'):
            period_key = 'day'

        # 快路径: K 线缓存
        cached = get_kline_cache(code, period_key)
        if cached:
            cached['rps_history'] = []
            cached['rps'] = {}
            rps_df = get_rps_data([code])
            if rps_df is not None and len(rps_df) > 0:
                row = rps_df.iloc[0]
                cached['rps'] = {
                    f'rps{p}': self._json_number(row.get(f'rps{p}'), None)
                    for p in [5, 10, 20, 50, 120, 250]
                    if f'rps{p}' in row.index
                }
            return cached

        # 慢路径: 从 stock_daily 实时算(历史兼容)
        df = get_daily_data_df([code], days=600)
        if df is None or df.empty:
            return None

        df = df[df['code'] == code].sort_values('date').reset_index(drop=True)
        if df.empty:
            return None

        # 周/月重采样
        if period_key != 'day':
            df = df.set_index('date')
            df = df.resample('W' if period_key == 'week' else 'M').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
                'amount': 'sum',
                'pre_close': 'last',
            }).dropna(subset=['close']).reset_index()

        close = df['close'].values.astype(float)
        high = df['high'].values.astype(float)
        low = df['low'].values.astype(float)

        ma5 = self._ma(close, 5)
        ma20 = self._ma(close, 20)
        ma60 = self._ma(close, 60)
        ma120 = self._ma(close, 120)
        ma250 = self._ma(close, 250)
        kdj = self._kdj(high, low, close)

        rps_df = get_rps_data([code])
        rps_dict: Dict[str, Any] = {}
        if rps_df is not None and len(rps_df) > 0:
            row = rps_df.iloc[0]
            for rps_period in [5, 10, 20, 50, 120, 250]:
                col = f'rps{rps_period}'
                if col in row.index:
                    val = row[col]
                    rps_dict[col] = self._json_number(val, None)

        def clean_value(value: Any, default: Any = None):
            return self._json_number(value, default)

        output_df = df.tail(60).copy() if period_key == 'day' else df
        rps_history_df = get_rps_history(
            code,
            days=len(output_df) if len(output_df) > 0 else 250,
        )

        def slice_indicator(values):
            cleaned = self._clean_numeric_list(values)
            if period_key == 'day':
                return cleaned[-len(output_df):]
            return cleaned

        return {
            'code': code,
            'period': period_key,
            'data': [
                {
                    'date': str(row['date'].date()) if hasattr(row['date'], 'date') else str(row['date'])[:10],
                    'open': clean_value(row.get('open'), 0.0),
                    'high': clean_value(row.get('high'), 0.0),
                    'low': clean_value(row.get('low'), 0.0),
                    'close': clean_value(row.get('close'), 0.0),
                    'volume': self._safe_int(row.get('volume'), 0),
                    'up': clean_value(row.get('up'), 0.0),
                }
                for _, row in output_df.iterrows()
            ],
            'rps_history': [
                {
                    'date': str(row['date'].date()) if hasattr(row['date'], 'date') else str(row['date'])[:10],
                    'rps50': self._optional_float(row.get('rps50')),
                    'rps120': self._optional_float(row.get('rps120')),
                    'rps250': self._optional_float(row.get('rps250')),
                }
                for _, row in rps_history_df.iterrows()
            ] if rps_history_df is not None and not rps_history_df.empty else [],
            'ma5': slice_indicator(ma5),
            'ma20': slice_indicator(ma20),
            'ma60': slice_indicator(ma60),
            'ma120': slice_indicator(ma120),
            'ma250': slice_indicator(ma250),
            'k': slice_indicator(kdj['K']) if kdj else [],
            'd': slice_indicator(kdj['D']) if kdj else [],
            'j': slice_indicator(kdj['J']) if kdj else [],
            'rps': rps_dict,
        }

    def _ma(self, arr, period: int):
        if len(arr) < period:
            return None
        result = np.full_like(arr, np.nan)
        for i in range(period - 1, len(arr)):
            result[i] = arr[i - period + 1:i + 1].mean()
        return result

    def _kdj(self, high, low, close):
        n = len(close)
        N = 9
        if n < N:
            return None

        import pandas as pd

        rsv = np.full(n, np.nan)
        for i in range(N - 1, n):
            ll = low[i - N + 1:i + 1].min()
            hh = high[i - N + 1:i + 1].max()
            rsv[i] = 50 if hh == ll else (close[i] - ll) / (hh - ll) * 100

        K = np.full(n, 50.0)
        D = np.full(n, 50.0)

        for i in range(1, n):
            if not np.isnan(rsv[i]):
                K[i] = 2 / 3 * K[i - 1] + 1 / 3 * rsv[i]
                D[i] = 2 / 3 * D[i - 1] + 1 / 3 * K[i]

        J = 3 * K - 2 * D
        return {'K': K, 'D': D, 'J': J}
