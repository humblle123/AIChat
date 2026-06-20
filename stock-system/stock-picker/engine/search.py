"""SearchMixin: 股票搜索 + 公式引擎接入。"""
from __future__ import annotations
import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from data.store import (
    get_stocks, get_daily_data, get_rps_data, get_latest_quote_snapshot,
    get_formula_template_by_id, get_formula_templates,
)
from strategies import get_strategy


class SearchMixin:
    """提供 `search()` 入口。"""

    def search(self, request: Dict[str, Any]) -> Dict[str, Any]:
        today = datetime.date.today().strftime('%Y-%m-%d')
        stock_df = get_stocks()
        if stock_df.empty:
            return self._empty_search_result(request, today)

        filters = request.get('filters') or {}
        markets = self._normalize_list(request.get('markets'))
        industries = self._normalize_list(request.get('industries'))
        concepts = self._normalize_list(request.get('concepts'))
        keyword = str(request.get('keyword') or '').strip()
        include_st = bool(filters.get('include_st', False))
        exclude_suspended = bool(filters.get('exclude_suspended', True))

        stock_df = self._apply_search_filters(
            stock_df=stock_df,
            markets=markets,
            industries=industries,
            concepts=concepts,
            keyword=keyword,
            include_st=include_st,
            exclude_suspended=exclude_suspended,
        )
        if stock_df.empty:
            return self._empty_search_result(request, today)

        template = None
        strategy_id = ''
        template_params = request.get('template_params') or {}
        formula = str(request.get('formula') or '').strip()
        template_id = request.get('template_id')

        if template_id:
            template = get_formula_template_by_id(int(template_id))
            if not template:
                return self._empty_search_result(request, today, error='模板不存在')
            strategy_id = template.get('strategy_id', '')
            strategy_params = self._merge_template_params(template, template_params)
        else:
            strategy_params = {}

        codes = stock_df['code'].astype(str).tolist()[:self.max_stocks]
        rps_df = get_rps_data(codes)
        stock_df = self._prefilter_for_strategy(
            stock_df=stock_df,
            strategy_id=strategy_id,
            rps_df=rps_df,
        )
        codes = stock_df['code'].astype(str).tolist()[:self.max_stocks]
        daily_data = get_daily_data(codes, days=600)
        quote_df = get_latest_quote_snapshot(codes)

        market_data = {
            'stock_list': stock_df,
            'daily_data': daily_data,
            'rps_data': rps_df,
            'quote_data': quote_df,
        }

        matched_signals: List[Dict[str, Any]] = []
        used_formula = formula

        if strategy_id:
            strategy = get_strategy(strategy_id, strategy_params)
            matched_signals = strategy.screen(market_data)
            used_formula = template.get('expression', formula) if template else formula
        elif formula:
            matched_signals = self._evaluate_formula_search(formula, market_data)
        else:
            matched_signals = self._build_filter_only_results(market_data)

        items = self._enrich_search_results(
            matched_signals=matched_signals,
            stock_df=stock_df,
            quote_df=quote_df,
            rps_df=rps_df,
            template_id=int(template_id) if template_id else (template.get('id') if template else None),
            strategy_id=strategy_id,
        )

        sort_by = str(request.get('sort_by') or 'change_pct')
        sort_order = str(request.get('sort_order') or 'desc').lower()
        items = self._sort_search_items(items, sort_by=sort_by, sort_order=sort_order)

        page = max(int(request.get('page') or 1), 1)
        page_size = max(int(request.get('page_size') or 20), 1)
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]

        return {
            'items': page_items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'sort_by': sort_by,
            'sort_order': sort_order,
            'applied_formula': used_formula,
            'applied_template': template,
        }

    def _apply_search_filters(
        self,
        stock_df: pd.DataFrame,
        markets: List[str],
        industries: List[str],
        concepts: List[str],
        keyword: str,
        include_st: bool,
        exclude_suspended: bool,
    ) -> pd.DataFrame:
        df = stock_df.copy()

        if markets and 'market' in df.columns:
            df = df[df['market'].fillna('').isin(markets)]
        if industries and 'industry' in df.columns:
            df = df[df['industry'].fillna('').isin(industries)]
        if keyword:
            mask = (
                df['code'].fillna('').astype(str).str.contains(keyword, case=False, na=False)
                | df['name'].fillna('').astype(str).str.contains(keyword, case=False, na=False)
            )
            df = df[mask]
        if not include_st and 'is_st' in df.columns:
            df = df[~df['is_st'].fillna(0).astype(int).astype(bool)]
        if exclude_suspended and 'is_suspended' in df.columns:
            df = df[~df['is_suspended'].fillna(0).astype(int).astype(bool)]
        if concepts and 'concept_tags' in df.columns:
            concept_mask = df['concept_tags'].fillna('[]').apply(
                lambda raw: bool(set(self._parse_concepts(raw)) & set(concepts))
            )
            df = df[concept_mask]
        return df.reset_index(drop=True)

    def _merge_template_params(self, template: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        params = {}
        schema = template.get('params_schema') or {}
        if isinstance(schema, dict):
            params.update(schema)
        if isinstance(override, dict):
            params.update(override)
        return params

    def _build_filter_only_results(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        stock_list = market_data.get('stock_list')
        if stock_list is None or stock_list.empty:
            return []
        results = []
        for _, row in stock_list.iterrows():
            code = str(row['code'])
            name = str(row.get('name', code))
            results.append({'code': code, 'name': name, 'reason': '基础筛选命中', 'metadata': {}})
        return results

    def _evaluate_formula_search(self, formula: str, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """用真实公式引擎对每只股票逐个求值。"""
        from formula_engine import evaluate_formula, FormulaError

        stock_list = market_data.get('stock_list')
        daily_data = market_data.get('daily_data', {}) or {}
        rps_df = market_data.get('rps_data')
        if stock_list is None or stock_list.empty or not daily_data:
            return []

        rps_map: Dict[str, Dict] = {}
        if rps_df is not None and not rps_df.empty:
            for _, row in rps_df.iterrows():
                rps_map[str(row['code'])] = row.to_dict()

        results: List[Dict[str, Any]] = []
        for _, row in stock_list.iterrows():
            code = str(row['code'])
            name = str(row.get('name', code))
            df = daily_data.get(code)
            if df is None or len(df) < 30:
                continue
            scalars = dict(rps_map.get(code, {}))
            try:
                hit, _ = evaluate_formula(formula, df, scalars)
            except FormulaError:
                continue
            if hit:
                results.append({'code': code, 'name': name, 'reason': formula[:30], 'metadata': {}})
        return results

    def _enrich_search_results(
        self,
        matched_signals: List[Dict[str, Any]],
        stock_df: pd.DataFrame,
        quote_df: pd.DataFrame,
        rps_df: pd.DataFrame,
        template_id: Optional[int],
        strategy_id: str,
    ) -> List[Dict[str, Any]]:
        from api.schemas import StockSearchItem
        from pydantic import ValidationError
        from logger import get_logger
        logger = get_logger(__name__)
        from data.store import get_daily_data_df

        stock_map = {str(row['code']): row.to_dict() for _, row in stock_df.iterrows()}
        quote_map = {}
        if quote_df is not None and not quote_df.empty:
            quote_map = {str(row['code']): row.to_dict() for _, row in quote_df.iterrows()}
        daily_map = {}
        latest_daily_df = get_daily_data_df(stock_df['code'].astype(str).tolist(), days=10)
        if latest_daily_df is not None and not latest_daily_df.empty:
            latest_daily_df = latest_daily_df.sort_values(['code', 'date'])
            latest_by_code = latest_daily_df.groupby('code').tail(1)
            daily_map = {str(row['code']): row.to_dict() for _, row in latest_by_code.iterrows()}
        rps_map = {}
        if rps_df is not None and not rps_df.empty:
            rps_map = {str(row['code']): row.to_dict() for _, row in rps_df.iterrows()}

        results = []
        for signal in matched_signals:
            code = str(signal.get('code'))
            base = stock_map.get(code, {})
            quote = quote_map.get(code, {})
            daily = daily_map.get(code, {})
            rps = rps_map.get(code, {})
            listed_date = base.get('listed_date') or base.get('list_date') or ''
            listed_days = 0
            if listed_date:
                try:
                    listed_days = max((pd.Timestamp.today().normalize() - pd.to_datetime(listed_date)).days, 0)
                except Exception:
                    listed_days = 0
            concept_tags = self._parse_concepts(base.get('concept_tags'))
            price = quote.get('price')
            if price is None:
                price = daily.get('close')
            if price is None and code in stock_map:
                price = quote.get('close') or base.get('price') or 0
            change_pct = quote.get('change_pct')
            if change_pct is None:
                change_pct = daily.get('up')
            if change_pct is None:
                change_pct = quote.get('up') or base.get('change_pct') or 0
            prev_close = self._normalize_prev_close(
                price=price,
                prev_close=(quote.get('prev_close') or quote.get('close')),
                change_pct=change_pct,
                fallback_prev_close=daily.get('pre_close'),
            )
            if price is not None and prev_close:
                change = float(price) - float(prev_close)
                change_pct = (float(price) - float(prev_close)) / float(prev_close) * 100
            else:
                change = quote.get('change') or 0.0
            results.append({
                'code': code,
                'name': base.get('name', signal.get('name', code)),
                'market': base.get('market', ''),
                'industry': base.get('industry', ''),
                'concept_tags': concept_tags,
                'security_type': base.get('security_type', 'stock'),
                'listed_date': listed_date,
                'listed_days': listed_days,
                'price': float(price or 0),
                'change': float(change or 0),
                'change_pct': float(change_pct or 0),
                'volume': int(quote.get('volume') or daily.get('volume') or 0),
                'amount': float(quote.get('amount') or daily.get('amount') or 0),
                'total_mv': float(quote.get('total_mv') or 0),
                'circ_mv': float(quote.get('circ_mv') or 0),
                'pe_ttm': quote.get('pe_ttm') or quote.get('pe'),
                'pb': quote.get('pb'),
                'roe_ttm': base.get('roe_ttm'),
                'revenue_yoy_q': base.get('revenue_yoy_q'),
                'net_profit_yoy_q': base.get('net_profit_yoy_q'),
                'rps50': rps.get('rps50'),
                'rps120': rps.get('rps120'),
                'rps250': rps.get('rps250'),
                'reason': signal.get('reason', ''),
                'template_id': template_id,
                'strategy_id': strategy_id,
            })

        # 出口校验(P2-7):每个 item 必须能塞进 StockSearchItem,缺字段立即暴露
        validated = []
        for item in results:
            try:
                validated.append(StockSearchItem(**item).model_dump())
            except ValidationError as e:
                logger.warning(f"搜索结果校验失败 code={item.get('code')}: {e}")
        return validated
