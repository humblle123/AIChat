"""b1 策略: KDJ_J < 阈值 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX (空谷幽兰)

向量化实现: 一次性把 daily_data 拼成长表,groupby 算 KDJ/EMA/SMA,
再对最后一行判断条件。5000 只股只跑 1 次 pandas。
"""
from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd
from strategies.base import BaseStrategy
from indicators import compute_kdj, compute_ema
from logger import get_logger

logger = get_logger(__name__)


class _ErrorCounter:
    """跨 screen() 调用的简单错误计数,run_daily_screen 跑完可看。"""
    _errors: Dict[str, int] = {}

    @classmethod
    def record(cls, strategy: str, code: str, exc: Exception) -> None:
        cls._errors[strategy] = cls._errors.get(strategy, 0) + 1
        logger.warning(f"{strategy} 评估 {code} 失败: {exc}", exc_info=False)

    @classmethod
    def summary(cls) -> Dict[str, int]:
        return dict(cls._errors)

    @classmethod
    def reset(cls) -> None:
        cls._errors.clear()


class B1Strategy(BaseStrategy):
    @property
    def id(self) -> str:
        return 'b1'

    @property
    def name(self) -> str:
        return '空谷幽兰'

    @property
    def description(self) -> str:
        return 'KDJ超卖 + 多空线突破,捕捉短期强势股'

    def screen(self, market_data: Dict) -> List[Dict]:
        stock_list = market_data.get('stock_list')
        daily_data = market_data.get('daily_data', {}) or {}
        rps_data = market_data.get('rps_data')

        if stock_list is None or stock_list.empty or not daily_data:
            return []

        j_threshold = float(self.params.get('j_threshold', 18))

        # 1) 拼长表
        parts = []
        for _, row in stock_list.iterrows():
            code = str(row['code'])
            df = daily_data.get(code)
            if df is None or df.empty:
                continue
            tmp = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
            tmp.insert(0, 'code', code)
            tmp['name'] = str(row.get('name', code))
            parts.append(tmp)
        if not parts:
            return []
        big = pd.concat(parts, ignore_index=True).sort_values(['code', 'date']).reset_index(drop=True)

        # 2) 一次性算指标
        big = compute_kdj(big)
        big = compute_ema(big, periods=(10,))

        # 3) ZXDQ = EMA(EMA(CLOSE, 10), 10);ZXDKX = (SMA14+SMA28+SMA57+SMA114)/4 (这里用普通 MA 等价)
        g = big.groupby('code', sort=False)['close']
        big['sma14'] = g.transform(lambda s: s.rolling(14, min_periods=14).mean())
        big['sma28'] = g.transform(lambda s: s.rolling(28, min_periods=28).mean())
        big['sma57'] = g.transform(lambda s: s.rolling(57, min_periods=57).mean())
        big['sma114'] = g.transform(lambda s: s.rolling(114, min_periods=114).mean())
        big['zxdkx'] = (big['sma14'] + big['sma28'] + big['sma57'] + big['sma114']) / 4

        # 4) 取每只股票最后一行
        last = big.groupby('code', sort=False).tail(1).reset_index(drop=True)

        # 5) 一次布尔筛选
        try:
            cond = (
                (last['kdj_j'] < j_threshold)
                & (last['close'] > last['zxdkx'])
                & (last['ema10'] > last['zxdkx'])
            )
        except Exception as e:
            _ErrorCounter.record('b1', '<batch>', e)
            return []

        hit = last[cond].copy()
        if hit.empty:
            return []

        # 6) 拼 rps 字典
        rps_map = {}
        if rps_data is not None and not rps_data.empty:
            for _, r in rps_data.iterrows():
                rps_map[str(r['code'])] = r.to_dict()

        results: List[Dict] = []
        for _, row in hit.iterrows():
            code = str(row['code'])
            rps = rps_map.get(code, {})
            j = float(row['kdj_j']) if pd.notna(row['kdj_j']) else None
            zxdkx = float(row['zxdkx']) if pd.notna(row['zxdkx']) else None
            change_pct = float(row.get('volume', 0))  # 兜底
            results.append(self.format_signal(
                code=code,
                name=str(row.get('name', code)),
                reason=f"B1: J={j:.1f}<{j_threshold}, C>{zxdkx:.2f}" if j is not None and zxdkx is not None else 'B1 命中',
                metadata={
                    'J': round(j, 2) if j is not None else None,
                    'RPS50': rps.get('rps50'),
                    'RPS120': rps.get('rps120'),
                    'RPS250': rps.get('rps250'),
                },
            ))
        return results
