"""s3 策略: RPS三线红

  RPS50 > min_rps50
  AND RPS120 > min_rps120
  AND RPS250 > min_rps250
  AND CLOSE / HHV(HIGH, 250) > near_high_threshold
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd
from strategies.base import BaseStrategy
from strategies.b1_strategy import _ErrorCounter
from logger import get_logger

logger = get_logger(__name__)


class S3Strategy(BaseStrategy):
    @property
    def id(self) -> str:
        return 's3'

    @property
    def name(self) -> str:
        return 'RPS三线红'

    @property
    def description(self) -> str:
        return 'RPS三线同时强势,长期上升趋势中的加速股'

    def screen(self, market_data: Dict) -> List[Dict]:
        stock_list = market_data.get('stock_list')
        daily_data = market_data.get('daily_data', {}) or {}
        rps_data = market_data.get('rps_data')

        if stock_list is None or stock_list.empty or not daily_data:
            return []
        if rps_data is None or rps_data.empty:
            return []

        min_rps50 = float(self.params.get('min_rps50', 90))
        min_rps120 = float(self.params.get('min_rps120', 93))
        min_rps250 = float(self.params.get('min_rps250', 95))
        near_threshold = float(self.params.get('near_high_threshold', 0.85))

        # 1) RPS 一次性筛选
        rps = rps_data.copy()
        rps['code'] = rps['code'].astype(str)
        rps_ok = rps[
            (rps['rps50'] > min_rps50)
            & (rps['rps120'] > min_rps120)
            & (rps['rps250'] > min_rps250)
        ]
        if rps_ok.empty:
            return []
        target_codes = set(rps_ok['code'].tolist())

        # 2) 只对命中的股票算 HHV250
        parts = []
        keep = []
        for _, row in stock_list.iterrows():
            code = str(row['code'])
            if code not in target_codes:
                continue
            df = daily_data.get(code)
            if df is None or len(df) < 250:
                continue
            tmp = df[['date', 'high', 'close']].copy()
            tmp.insert(0, 'code', code)
            tmp['name'] = str(row.get('name', code))
            parts.append(tmp)
        if not parts:
            return []
        big = pd.concat(parts, ignore_index=True).sort_values(['code', 'date']).reset_index(drop=True)

        g = big.groupby('code', sort=False)
        big['hhv250'] = g['high'].transform(lambda s: s.rolling(250, min_periods=250).max())
        last = g.tail(1).reset_index(drop=True)

        # 3) 距离 250 日高点比例
        try:
            last = last[last['hhv250'] > 0].copy()
            last['near_rate'] = last['close'] / last['hhv250']
            hit = last[last['near_rate'] > near_threshold]
        except Exception as e:
            _ErrorCounter.record('s3', '<batch>', e)
            return []
        if hit.empty:
            return []

        rps_map = {str(r['code']): r.to_dict() for _, r in rps_ok.iterrows()}
        results: List[Dict] = []
        for _, row in hit.iterrows():
            code = str(row['code'])
            rps = rps_map[code]
            results.append(self.format_signal(
                code=code,
                name=str(row.get('name', code)),
                reason=f"三线红: RPS50={rps.get('rps50'):.1f} RPS120={rps.get('rps120'):.1f} RPS250={rps.get('rps250'):.1f}",
                metadata={
                    'RPS50': rps.get('rps50'),
                    'RPS120': rps.get('rps120'),
                    'RPS250': rps.get('rps250'),
                    'near_250high': round(float(row['near_rate']) * 100, 1),
                },
            ))
        return results
