"""DetailMixin: 股票详情页组装。"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from data.store import (
    get_stock_basic_by_code, get_daily_data_df, get_latest_quote_snapshot,
    get_rps_data, get_rps_history, get_formula_templates,
)
from strategies import get_strategy


class DetailMixin:
    """提供 `get_stock_detail()`。"""

    def get_stock_detail(self, code: str) -> Optional[Dict[str, Any]]:
        code = str(code or '').strip()
        if not code:
            return None

        basic = get_stock_basic_by_code(code)
        if not basic:
            return None
        if basic.get('security_type') and basic.get('security_type') != 'stock':
            return None
        if basic.get('is_delisted'):
            return None

        daily_df = get_daily_data_df([code], days=600)
        if daily_df is None:
            daily_df = pd.DataFrame()
        if not daily_df.empty:
            daily_df = daily_df.sort_values('date').reset_index(drop=True)

        quote_df = get_latest_quote_snapshot([code])
        quote_row = quote_df.iloc[0].to_dict() if quote_df is not None and not quote_df.empty else {}

        rps_df = get_rps_data([code])
        rps_row = rps_df.iloc[0].to_dict() if rps_df is not None and not rps_df.empty else {}
        rps_history_df = get_rps_history(
            code,
            days=len(daily_df) if daily_df is not None and not daily_df.empty else 250,
        )

        last_row = daily_df.iloc[-1] if not daily_df.empty else None
        quote = self._build_detail_quote(quote_row, last_row)
        fundamentals = self._build_detail_fundamentals(basic, quote_row)
        technicals = self._build_detail_technicals(daily_df, rps_row)
        kline_summary = self._build_kline_summary(daily_df, quote)
        template_hits = self._build_template_hits(code, basic, daily_df, rps_df)

        applied_date = quote.get('trade_date') or kline_summary.get('last_trade_date') or ''
        listed_date = basic.get('listed_date') or basic.get('list_date') or ''
        listed_days = 0
        if listed_date:
            try:
                listed_days = max((pd.Timestamp.today().normalize() - pd.to_datetime(listed_date)).days, 0)
            except Exception:
                listed_days = 0

        basic_payload = {
            'code': code,
            'name': basic.get('name', ''),
            'market': basic.get('market', ''),
            'industry': basic.get('industry', ''),
            'concept_tags': self._parse_concepts(basic.get('concept_tags')),
            'security_type': basic.get('security_type', 'stock'),
            'listed_date': listed_date,
            'listed_days': listed_days,
            'is_delisted': bool(basic.get('is_delisted', 0)),
            'is_st': bool(basic.get('is_st', 0)),
            'is_suspended': bool(basic.get('is_suspended', 0)),
        }

        return {
            'basic': basic_payload,
            'quote': quote,
            'fundamentals': fundamentals,
            'technicals': technicals,
            'kline_summary': kline_summary,
            'template_hits': template_hits,
            'applied_date': applied_date,
        }

    def _build_detail_quote(self, quote_row: Dict[str, Any], last_row: Optional[pd.Series]) -> Dict[str, Any]:
        fallback_close = self._safe_float(last_row.get('close') if last_row is not None else None, 0.0)
        fallback_prev_close = self._safe_float(last_row.get('pre_close') if last_row is not None else None, 0.0)
        fallback_open = self._safe_float(last_row.get('open') if last_row is not None else None, fallback_close)
        fallback_high = self._safe_float(last_row.get('high') if last_row is not None else None, fallback_close)
        fallback_low = self._safe_float(last_row.get('low') if last_row is not None else None, fallback_close)
        fallback_volume = self._safe_int(last_row.get('volume') if last_row is not None else None, 0)
        fallback_amount = self._safe_float(last_row.get('amount') if last_row is not None else None, 0.0)
        fallback_trade_date = self._format_date(last_row.get('date')) if last_row is not None else ''

        price = self._safe_float(quote_row.get('price'), fallback_close)
        prev_close = self._safe_float(quote_row.get('prev_close'), fallback_prev_close)
        close = self._safe_float(quote_row.get('close'), fallback_close)
        change = quote_row.get('change')
        if change is None and price is not None and prev_close is not None:
            change = price - prev_close

        change_pct = quote_row.get('change_pct')
        if change_pct is None:
            if prev_close:
                change_pct = (price - prev_close) / prev_close * 100
            else:
                change_pct = self._safe_float(last_row.get('up') if last_row is not None else None, 0.0)

        prev_close = self._normalize_prev_close(
            price=price,
            prev_close=prev_close,
            change_pct=change_pct,
            fallback_prev_close=fallback_prev_close,
        )
        change = self._safe_float(price, fallback_close) - prev_close
        if prev_close:
            change_pct = (self._safe_float(price, fallback_close) - prev_close) / prev_close * 100

        trade_date = str(quote_row.get('trade_date') or fallback_trade_date or '')

        return {
            'trade_date': trade_date,
            'price': self._safe_float(price, fallback_close),
            'prev_close': prev_close,
            'change': self._safe_float(change, 0.0),
            'change_pct': self._safe_float(change_pct, 0.0),
            'volume': self._safe_int(quote_row.get('volume'), fallback_volume),
            'amount': self._safe_float(quote_row.get('amount'), fallback_amount),
            'open': self._safe_float(quote_row.get('open'), fallback_open),
            'high': self._safe_float(quote_row.get('high'), fallback_high),
            'low': self._safe_float(quote_row.get('low'), fallback_low),
            'close': close,
            'pe': self._optional_float(quote_row.get('pe_ttm') or quote_row.get('pe')),
            'pb': self._optional_float(quote_row.get('pb')),
            'total_mv': self._optional_float(quote_row.get('total_mv')),
            'circ_mv': self._optional_float(quote_row.get('circ_mv')),
        }

    def _normalize_prev_close(
        self,
        price,
        prev_close,
        change_pct,
        fallback_prev_close,
    ) -> float:
        current_price = self._safe_float(price, 0.0)
        prev_value = self._safe_float(prev_close, 0.0)
        fallback_value = self._safe_float(fallback_prev_close, 0.0)
        pct_value = self._optional_float(change_pct)

        if current_price > 0 and prev_value > 0:
            ratio = prev_value / current_price
            if 0.2 <= ratio <= 5:
                return prev_value

        if current_price > 0 and pct_value is not None and -20 <= pct_value <= 20:
            denominator = 1 + pct_value / 100
            if abs(denominator) > 1e-9:
                inferred = current_price / denominator
                if inferred > 0 and 0.2 <= inferred / current_price <= 5:
                    return inferred

        if current_price > 0 and fallback_value > 0 and 0.2 <= fallback_value / current_price <= 5:
            return fallback_value

        return prev_value if prev_value > 0 else fallback_value

    def _build_detail_fundamentals(self, basic: Dict[str, Any], quote_row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'pe_ttm': self._optional_float(quote_row.get('pe_ttm') or quote_row.get('pe')),
            'pb': self._optional_float(quote_row.get('pb')),
            'roe_ttm': self._optional_float(basic.get('roe_ttm')),
            'revenue_yoy_q': self._optional_float(basic.get('revenue_yoy_q')),
            'net_profit_yoy_q': self._optional_float(basic.get('net_profit_yoy_q')),
            'debt_ratio': self._optional_float(basic.get('debt_ratio')),
            'report_period': str(basic.get('report_period') or ''),
        }

    def _build_detail_technicals(self, daily_df: pd.DataFrame, rps_row: Dict[str, Any]) -> Dict[str, Any]:
        empty = {
            'ma5': None, 'ma20': None, 'ma60': None, 'ma120': None, 'ma250': None,
            'rsi14': None, 'macd_dif': None, 'macd_dea': None, 'macd_hist': None,
            'volume_ratio_1d': None, 'avg_volume_5d': None,
            'kdj_k': None, 'kdj_d': None, 'kdj_j': None,
            'rps50': self._optional_float(rps_row.get('rps50')),
            'rps120': self._optional_float(rps_row.get('rps120')),
            'rps250': self._optional_float(rps_row.get('rps250')),
        }
        if daily_df is None or daily_df.empty:
            return empty

        from indicators import compute_ma, compute_macd, compute_rsi, compute_kdj

        work = daily_df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        work.insert(0, 'code', '_detail')
        work = compute_ma(work)
        work = compute_macd(work)
        work = compute_rsi(work)
        work = compute_kdj(work)
        last = work.iloc[-1]

        volume = work['volume'].astype(float).values
        avg_volume_5d = None
        volume_ratio_1d = None
        if len(volume) > 6:
            history = volume[-6:-1]
            mean = float(np.nanmean(history))
            if mean > 0:
                avg_volume_5d = mean
                volume_ratio_1d = float(volume[-1] / mean)

        def _v(col: str):
            v = last.get(col)
            return self._optional_float(v)

        return {
            'ma5': _v('ma5'), 'ma20': _v('ma20'), 'ma60': _v('ma60'),
            'ma120': _v('ma120'), 'ma250': _v('ma250'),
            'rsi14': _v('rsi14'),
            'macd_dif': _v('macd_dif'), 'macd_dea': _v('macd_dea'), 'macd_hist': _v('macd_hist'),
            'volume_ratio_1d': self._safe_float(volume_ratio_1d, None),
            'avg_volume_5d': self._safe_float(avg_volume_5d, None),
            'kdj_k': _v('kdj_k'), 'kdj_d': _v('kdj_d'), 'kdj_j': _v('kdj_j'),
            'rps50': self._optional_float(rps_row.get('rps50')),
            'rps120': self._optional_float(rps_row.get('rps120')),
            'rps250': self._optional_float(rps_row.get('rps250')),
        }

    def _build_kline_summary(self, daily_df: pd.DataFrame, quote: Dict[str, Any]) -> Dict[str, Any]:
        if daily_df is None or daily_df.empty:
            return {
                'last_trade_date': quote.get('trade_date', ''),
                'last_close': self._safe_float(quote.get('close'), 0.0),
                'highest_250d': None,
                'lowest_250d': None,
                'day_count': 0,
            }

        recent = daily_df.tail(250)
        last_row = daily_df.iloc[-1]
        return {
            'last_trade_date': self._format_date(last_row.get('date')),
            'last_close': self._safe_float(last_row.get('close'), quote.get('close', 0.0)),
            'highest_250d': self._safe_float(recent['high'].max(), None) if 'high' in recent.columns else None,
            'lowest_250d': self._safe_float(recent['low'].min(), None) if 'low' in recent.columns else None,
            'day_count': int(len(daily_df)),
        }

    def _build_template_hits(self, code: str, basic: Dict[str, Any], daily_df: pd.DataFrame, rps_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """读取当前股票的 template_hits。

        优先从 template_screen_cache.template_hits_json 读盘后预计算结果;
        缓存缺失时降级到实时跑 4 个内置策略(慢路径)。
        """
        # 快路径: 读盘后预计算
        from data.store import get_template_hits_for_code
        cached = get_template_hits_for_code(code)
        if cached:
            return cached

        # 慢路径: 实时计算
        template_hits: List[Dict[str, Any]] = []
        if daily_df is None or daily_df.empty:
            return template_hits

        stock_list = pd.DataFrame([{
            'code': code,
            'name': basic.get('name', code),
            'market': basic.get('market', ''),
            'industry': basic.get('industry', ''),
            'concept_tags': basic.get('concept_tags', []),
            'security_type': basic.get('security_type', 'stock'),
            'listed_date': basic.get('listed_date', ''),
            'is_delisted': basic.get('is_delisted', 0),
            'is_st': basic.get('is_st', 0),
            'is_suspended': basic.get('is_suspended', 0),
        }])
        market_data = {
            'stock_list': stock_list,
            'daily_data': {code: daily_df},
            'rps_data': rps_df,
        }

        for template in get_formula_templates():
            if not template.get('enabled', 1):
                continue
            strategy_id = template.get('strategy_id', '')
            try:
                strategy = get_strategy(strategy_id, template.get('params_schema', {}))
            except Exception:
                continue
            try:
                signals = strategy.screen(market_data)
            except Exception:
                signals = []
            if not signals:
                continue
            signal = signals[0]
            template_hits.append({
                'template_id': template.get('id'),
                'strategy_id': strategy_id,
                'name': template.get('name', ''),
                'group_name': template.get('group_name', ''),
                'reason': signal.get('reason', ''),
                'matched': True,
                'params': template.get('params_schema', {}) or {},
            })

        return template_hits
