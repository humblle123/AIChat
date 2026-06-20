"""CacheMixin: 模板预计算缓存读。"""
from __future__ import annotations
import datetime
from typing import Any, Dict, List, Optional

from data.store import (
    get_formula_template_by_id, get_template_screen_result_page,
    get_template_screen_results, get_latest_date, get_stocks_by_codes,
)


class CacheMixin:
    """提供 `get_cached_template_results()`。"""

    def get_cached_template_results(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """读取内置模板预计算缓存。新缓存直接读快照,旧缓存降级富化。"""
        template_id = request.get('template_id')
        if not template_id:
            today = get_latest_date() or datetime.date.today().strftime('%Y-%m-%d')
            return self._empty_search_result(request, today, error='缺少模板ID')

        template = get_formula_template_by_id(int(template_id))
        if not template:
            today = get_latest_date() or datetime.date.today().strftime('%Y-%m-%d')
            return self._empty_search_result(request, today, error='模板不存在')

        filters = request.get('filters') or {}
        markets = self._normalize_list(request.get('markets'))
        industries = self._normalize_list(request.get('industries'))
        concepts = self._normalize_list(request.get('concepts'))
        keyword = str(request.get('keyword') or '').strip()
        include_st = bool(filters.get('include_st', False))
        exclude_suspended = bool(filters.get('exclude_suspended', True))
        sort_by = str(request.get('sort_by') or 'change_pct')
        sort_order = str(request.get('sort_order') or 'desc').lower()
        page = max(int(request.get('page') or 1), 1)
        page_size = max(int(request.get('page_size') or 20), 1)

        if not concepts:
            page_payload = get_template_screen_result_page(
                template_id=int(template_id),
                date=request.get('date'),
                sort_by=sort_by,
                sort_order=sort_order,
                page=page,
                page_size=page_size,
                markets=markets,
                industries=industries,
                keyword=keyword,
                include_st=include_st,
                exclude_suspended=exclude_suspended,
            )
            snapshot_items = page_payload.get('items', [])
            snapshot_date = page_payload.get('date') or request.get('date') or datetime.date.today().strftime('%Y-%m-%d')
            has_snapshot_fields = any(
                item.get('price') not in (None, 0, 0.0) or item.get('rps50') is not None
                for item in snapshot_items
            )
            if snapshot_items and has_snapshot_fields:
                return {
                    'items': snapshot_items,
                    'total': page_payload.get('total', 0),
                    'page': page,
                    'page_size': page_size,
                    'sort_by': sort_by,
                    'sort_order': sort_order,
                    'applied_formula': template.get('expression', ''),
                    'applied_template': template,
                    'date': snapshot_date,
                    'cache_hit': True,  # 真正命中: 缓存非空 + 字段齐全
                }
            if not snapshot_items and page_payload.get('total', 0) == 0:
                return {
                    **self._empty_search_result(request, snapshot_date),
                    'applied_template': template,
                    'applied_formula': template.get('expression', ''),
                    'date': snapshot_date,
                    'cache_hit': False,  # 缓存确实为空
                }
            if not snapshot_items and page_payload.get('total', 0) > 0:
                return {
                    'items': [],
                    'total': page_payload.get('total', 0),
                    'page': page,
                    'page_size': page_size,
                    'sort_by': sort_by,
                    'sort_order': sort_order,
                    'applied_formula': template.get('expression', ''),
                    'applied_template': template,
                    'date': snapshot_date,
                    'cache_hit': True,  # 总数>0 但本页为空,说明缓存存在,只是分页越界
                }

        today = get_latest_date() or datetime.date.today().strftime('%Y-%m-%d')
        cache_payload = get_template_screen_results(int(template_id), request.get('date'))
        cache_items = cache_payload.get('items', [])
        cache_date = cache_payload.get('date') or today
        if not cache_items:
            return {
                **self._empty_search_result(request, cache_date),
                'applied_template': template,
                'applied_formula': template.get('expression', ''),
                'date': cache_date,
                'cache_hit': False,
            }

        stock_df = get_stocks_by_codes([str(item.get('code')) for item in cache_items])
        if stock_df.empty:
            return {
                **self._empty_search_result(request, cache_date),
                'applied_template': template,
                'applied_formula': template.get('expression', ''),
                'date': cache_date,
                'cache_hit': True,
            }

        stock_df = self._apply_search_filters(
            stock_df=stock_df,
            markets=markets,
            industries=industries,
            concepts=concepts,
            keyword=keyword,
            include_st=include_st,
            exclude_suspended=exclude_suspended,
        )

        allowed_codes = set(stock_df['code'].astype(str).tolist())
        filtered_cache_items = [item for item in cache_items if str(item.get('code')) in allowed_codes]
        if not filtered_cache_items:
            return {
                **self._empty_search_result(request, cache_date),
                'applied_template': template,
                'applied_formula': template.get('expression', ''),
                'date': cache_date,
                'cache_hit': True,
            }

        stock_map = {
            str(row['code']): row.to_dict()
            for _, row in stock_df.iterrows()
        }
        items = []
        for item in filtered_cache_items:
            code = str(item.get('code'))
            stock_row = stock_map.get(code, {})
            listed_date = stock_row.get('listed_date', item.get('listed_date', '')) or ''
            items.append({
                'code': code,
                'name': item.get('name') or stock_row.get('name', ''),
                'market': stock_row.get('market', item.get('market', '')) or '',
                'industry': stock_row.get('industry', item.get('industry', '')) or '',
                'concept_tags': self._parse_concept_tags(
                    stock_row.get('concept_tags', item.get('concept_tags', []))
                ),
                'security_type': stock_row.get('security_type', item.get('security_type', 'stock')) or 'stock',
                'listed_date': listed_date,
                'listed_days': self._listed_days(listed_date),
                'price': float(item.get('price') or 0),
                'change': float(item.get('change') or 0),
                'change_pct': float(item.get('change_pct') or 0),
                'volume': int(item.get('volume') or 0),
                'amount': float(item.get('amount') or 0),
                'total_mv': float(item.get('total_mv') or 0),
                'circ_mv': float(item.get('circ_mv') or 0),
                'pe_ttm': item.get('pe_ttm'),
                'pb': item.get('pb'),
                'roe_ttm': item.get('roe_ttm'),
                'revenue_yoy_q': item.get('revenue_yoy_q'),
                'net_profit_yoy_q': item.get('net_profit_yoy_q'),
                'rps50': item.get('rps50'),
                'rps120': item.get('rps120'),
                'rps250': item.get('rps250'),
                'reason': item.get('reason', ''),
                'template_id': int(template_id),
                'strategy_id': str(template.get('strategy_id') or ''),
                'metadata': item.get('metadata', {}) or {},
            })

        items = self._sort_search_items(items, sort_by=sort_by, sort_order=sort_order)

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            'items': items[start:end],
            'total': total,
            'page': page,
            'page_size': page_size,
            'sort_by': sort_by,
            'sort_order': sort_order,
            'applied_formula': template.get('expression', ''),
            'applied_template': template,
            'date': cache_date,
            'cache_hit': True,
        }

    def _listed_days(self, listed_date: str) -> int:
        if not listed_date:
            return 0
        try:
            import pandas as pd
            return max((pd.Timestamp.today().normalize() - pd.to_datetime(listed_date)).days, 0)
        except Exception:
            return 0
