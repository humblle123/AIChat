"""ScreeningMixin: 选股主流程 + 策略引擎调度。"""
from __future__ import annotations
import datetime
import json
from typing import Any, Dict, List, Optional

import pandas as pd

from data.store import (
    get_stocks, get_rps_data, get_daily_data, get_daily_data_df,
    save_screen_result, get_latest_date,
)
from strategies import get_strategy
from logger import get_logger

logger = get_logger(__name__)


class ScreeningMixin:
    """提供 `screen()` 选股主流程。"""

    def screen(self, strategies: List[str], params: Dict[str, Dict] = None, formula_id: int = None) -> Dict:
        params = params or {}
        today = get_latest_date() or datetime.date.today().strftime('%Y-%m-%d')

        stock_df = get_stocks()
        if stock_df.empty:
            return {'date': today, 'strategies': {}, 'signals': [], 'total': 0}

        # 排除 ST / 退市 / 非股票(用字段判断,见 P1-10)
        if 'is_st' in stock_df.columns:
            stock_df = stock_df[~stock_df['is_st'].fillna(0).astype(bool)]
        if 'is_delisted' in stock_df.columns:
            stock_df = stock_df[~stock_df['is_delisted'].fillna(0).astype(bool)]
        if 'security_type' in stock_df.columns:
            stock_df = stock_df[stock_df['security_type'].fillna('stock') == 'stock']

        codes = stock_df['code'].astype(str).tolist()[:self.max_stocks]
        logger.info(f"扫描 {len(codes)} 只股票...")

        rps_df = get_rps_data(codes)
        signals: List[Dict] = []
        strategies_result: Dict[str, Dict[str, Any]] = {}

        for strategy in strategies:
            strategy_key = str(strategy).strip().lower()
            strategy_name = strategy_key

            if strategy_key in {'b1', 's2', 's3', 'kd1'}:
                strategy_params = params.get(strategy_key) or params.get(strategy) or {}
                strategy_impl = get_strategy(strategy_key, strategy_params)
                strategy_name = strategy_impl.name

                candidate_df = self._prefilter_for_strategy(
                    stock_df=stock_df,
                    strategy_id=strategy_key,
                    rps_df=rps_df,
                )
                candidate_codes = candidate_df['code'].astype(str).tolist()[:self.max_stocks]
                candidate_daily = get_daily_data(candidate_codes, days=600) if candidate_codes else {}
                candidate_rps = None
                if rps_df is not None and len(rps_df) > 0 and candidate_codes:
                    candidate_rps = rps_df[rps_df['code'].astype(str).isin(candidate_codes)].copy()

                filtered = strategy_impl.screen({
                    'stock_list': candidate_df,
                    'daily_data': candidate_daily,
                    'rps_data': candidate_rps,
                    'quote_data': None,
                })
            elif rps_df is None or len(rps_df) == 0:
                filtered = []
            else:
                filtered = []

            strategies_result[strategy_key] = {
                'name': strategy_name,
                'count': len(filtered),
                'signals': filtered,
            }
            signals.extend(filtered)

        # 去重
        seen = set()
        unique_signals = []
        for s in signals:
            if s['code'] not in seen:
                seen.add(s['code'])
                unique_signals.append(s)

        latest_daily = get_daily_data_df([s['code'] for s in unique_signals], days=5) if unique_signals else pd.DataFrame()
        if latest_daily is not None and len(latest_daily) > 0:
            latest_by_code = latest_daily.groupby('code').last()
            for signal in unique_signals:
                code = signal['code']
                if code in latest_by_code.index:
                    latest = latest_by_code.loc[code]
                    signal['price'] = latest['close']
                    signal['change'] = latest['up'] if 'up' in latest.index else 0

        if formula_id:
            save_screen_result(today, formula_id, unique_signals)

        return {
            'date': today,
            'strategies': strategies_result,
            'signals': unique_signals,
            'total': len(unique_signals),
        }

    def _prefilter_for_strategy(
        self,
        stock_df: pd.DataFrame,
        strategy_id: str,
        rps_df: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """用便宜的 RPS 条件先缩小候选集,避免全量逐股跑策略。"""
        if stock_df is None or stock_df.empty or not strategy_id:
            return stock_df
        if rps_df is None or len(rps_df) == 0:
            return stock_df

        candidate = rps_df.copy()
        strategy_id = str(strategy_id).lower()

        if strategy_id == 's3':
            candidate = candidate[
                (candidate['rps50'] >= 85)
                & (candidate['rps120'] >= 88)
                & (candidate['rps250'] >= 90)
            ]
        elif strategy_id == 'kd1':
            candidate = candidate[
                (candidate['rps50'] >= 90)
                | (candidate['rps120'] >= 90)
                | (candidate['rps250'] >= 90)
            ]
        elif strategy_id == 's2':
            candidate = candidate[candidate['rps50'] >= 75]
        elif strategy_id == 'b1':
            candidate = candidate[candidate['rps50'] >= 60]

        candidate_codes = set(candidate['code'].astype(str).tolist())
        if not candidate_codes:
            return stock_df.iloc[0:0].copy()

        filtered = stock_df[stock_df['code'].astype(str).isin(candidate_codes)].copy()
        return filtered.reset_index(drop=True)

    def build_template_result_snapshot(
        self,
        matched_signals: List[Dict[str, Any]],
        template_id: int,
        strategy_id: str,
    ) -> List[Dict[str, Any]]:
        """把策略命中结果富化成前端可直接展示的缓存快照。

        同时计算每只股票的 template_hits(用真实公式引擎对 4 个内置模板逐个评估),
        序列化到 template_hits_json 字段落库,详情页直接读。
        """
        from data.store import get_stocks_by_codes, get_latest_quote_snapshot, get_rps_data, get_daily_data_df
        from formula_engine import evaluate_formula, FormulaError
        from data.store import get_formula_templates

        codes = [str(signal.get('code')) for signal in matched_signals if signal.get('code')]
        if not codes:
            return []

        stock_df = get_stocks_by_codes(codes)
        if stock_df.empty:
            return []

        quote_df = get_latest_quote_snapshot(codes)
        rps_df = get_rps_data(codes)

        # 计算每只股票对所有 4 个模板的命中,落 template_hits_json
        rps_map = {}
        if rps_df is not None and not rps_df.empty:
            for _, r in rps_df.iterrows():
                rps_map[str(r['code'])] = r.to_dict()
        daily_map = get_daily_data_df(codes, days=300) if codes else None
        per_code_daily = {}
        if daily_map is not None and not daily_map.empty:
            for code, group in daily_map.groupby('code'):
                per_code_daily[str(code)] = group.sort_values('date').reset_index(drop=True)

        templates = get_formula_templates()
        per_code_hits: Dict[str, List[Dict[str, Any]]] = {c: [] for c in codes}
        for tpl in templates:
            if not tpl.get('enabled', 1):
                continue
            expr = tpl.get('expression', '')
            tpl_id = tpl.get('id')
            tpl_name = tpl.get('name', '')
            tpl_group = tpl.get('group_name', '')
            tpl_strategy = tpl.get('strategy_id', '')
            for code in codes:
                df = per_code_daily.get(code)
                if df is None or len(df) < 30:
                    continue
                scalars = dict(rps_map.get(code, {}))
                try:
                    hit, info = evaluate_formula(expr, df, scalars)
                except FormulaError:
                    hit = False
                    info = {}
                if hit:
                    per_code_hits[code].append({
                        'template_id': tpl_id,
                        'strategy_id': tpl_strategy,
                        'name': tpl_name,
                        'group_name': tpl_group,
                        'reason': str(expr)[:60],
                        'matched': True,
                    })

        # 调 _enrich_search_results 拿到基础富化字段,再补 template_hits_json
        items = self._enrich_search_results(
            matched_signals=matched_signals,
            stock_df=stock_df,
            quote_df=quote_df,
            rps_df=rps_df,
            template_id=template_id,
            strategy_id=strategy_id,
        )
        # 强制把 template_hits_json 注入每个 item
        for item in items:
            item['template_hits_json'] = json.dumps(per_code_hits.get(item['code'], []), ensure_ascii=False)
        return items
