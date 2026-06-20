"""s2 策略: 月线反转

  CLOSE > MA(CLOSE, 250)
  AND COUNT(HIGH >= HHV(HIGH, 50), 30) > 0      (30日内创过50日新高)
  AND RPS50 >= min_rps50
  AND COUNT(CLOSE > MA(CLOSE, 250), 30) in (min_above_days, max_above_days)
  AND CLOSE / HHV(HIGH, 100) > 0.9
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd
from strategies.base import BaseStrategy
from strategies.b1_strategy import _ErrorCounter
from logger import get_logger

logger = get_logger(__name__)


class S2Strategy(BaseStrategy):
    @property
    def id(self) -> str:
        return 's2'

    @property
    def name(self) -> str:
        return '月线反转'

    @property
    def description(self) -> str:
        return '站上年线 + 创50日新高,经典趋势突破形态'

    def screen(self, market_data: Dict) -> List[Dict]:
        stock_list = market_data.get('stock_list')
        daily_data = market_data.get('daily_data', {}) or {}
        rps_data = market_data.get('rps_data')

        if stock_list is None or stock_list.empty or not daily_data:
            return []

        ma_period = int(self.params.get('ma_period', 250))
        new_high_days = int(self.params.get('new_high_days', 50))
        min_rps50 = float(self.params.get('min_rps50', 85))
        min_above_days = int(self.params.get('min_above_ma_days', 2))
        max_above_days = int(self.params.get('max_above_ma_days', 30))

        parts = []
        for _, row in stock_list.iterrows():
            code = str(row['code'])
            df = daily_data.get(code)
            if df is None or len(df) < ma_period + 30:
                continue
            tmp = df[['date', 'high', 'close']].copy()
            tmp.insert(0, 'code', code)
            tmp['name'] = str(row.get('name', code))
            parts.append(tmp)
        if not parts:
            return []
        big = pd.concat(parts, ignore_index=True).sort_values(['code', 'date']).reset_index(drop=True)

        g = big.groupby('code', sort=False)
        big['ma250'] = g['close'].transform(lambda s: s.rolling(ma_period, min_periods=ma_period).mean())
        big['hhv50'] = g['high'].transform(lambda s: s.rolling(new_high_days, min_periods=new_high_days).max())
        big['hhv100'] = g['high'].transform(lambda s: s.rolling(100, min_periods=100).max())

        # 30 日滚动统计
        big['above_ma'] = (big['close'] > big['ma250']).astype(int)
        big['new_high'] = (big['high'] >= big['hhv50']).astype(int)
        g2 = big.groupby('code', sort=False)
        big['cnt_above_ma_30'] = g2['above_ma'].transform(lambda s: s.rolling(30, min_periods=30).sum())
        big['cnt_new_high_30'] = g2['new_high'].transform(lambda s: s.rolling(30, min_periods=30).sum())

        last = g2.tail(1).reset_index(drop=True)

        # RPS 预筛
        rps_map = {}
        try:
            if rps_data is not None and not rps_data.empty:
                for _, r in rps_data.iterrows():
                    rps_map[str(r['code'])] = r.to_dict()
        except Exception as e:
            _ErrorCounter.record('s2', '<rps_build>', e)

        results: List[Dict] = []
        for _, row in last.iterrows():
            try:
                code = str(row['code'])
                rps = rps_map.get(code, {})
                rps50 = rps.get('rps50')
                if rps50 is None or pd.isna(rps50) or float(rps50) < min_rps50:
                    continue
                ma250 = row['ma250']
                if pd.isna(ma250) or float(ma250) <= 0:
                    continue
                if float(row['close']) <= float(ma250):
                    continue
                cnt_above = int(row['cnt_above_ma_30']) if pd.notna(row['cnt_above_ma_30']) else 0
                cnt_new_high = int(row['cnt_new_high_30']) if pd.notna(row['cnt_new_high_30']) else 0
                if not (min_above_days < cnt_above < max_above_days):
                    continue
                if cnt_new_high <= 0:
                    continue
                hhv100 = row['hhv100']
                if pd.isna(hhv100) or float(hhv100) <= 0:
                    continue
                if float(row['close']) / float(hhv100) <= 0.9:
                    continue
                results.append(self.format_signal(
                    code=code,
                    name=str(row.get('name', code)),
                    reason=f"月线反转: 站年线, 30日内{cnt_new_high}次新高, RPS50={float(rps50):.0f}",
                    metadata={
                        'RPS50': rps50,
                        'RPS120': rps.get('rps120'),
                        'RPS250': rps.get('rps250'),
                        'new_high_days': cnt_new_high,
                        'above_ma_days': cnt_above,
                    },
                ))
            except Exception as e:
                _ErrorCounter.record('s2', str(row.get('code', '?')), e)
                continue
        return results
