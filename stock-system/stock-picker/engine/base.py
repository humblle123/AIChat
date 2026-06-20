"""ScreeningEngine 主类、通用工具方法(_safe_float / _format_date 等)。"""
from __future__ import annotations
import datetime
import json
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from data.store import get_latest_date


class ScreeningEngine:
    """选股引擎(主类,挂载各子模块的方法)。"""

    def __init__(self, max_stocks: int = 6000):
        self.max_stocks = max_stocks

    # ====== 公共工具方法 ======

    def _safe_float(self, value: Any, default: Optional[float] = 0.0) -> Optional[float]:
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        try:
            return float(value)
        except Exception:
            return default

    def _optional_float(self, value: Any) -> Optional[float]:
        return self._safe_float(value, None)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        try:
            return int(float(value))
        except Exception:
            return default

    def _format_date(self, value: Any) -> str:
        if value is None:
            return ''
        try:
            ts = pd.to_datetime(value)
            return ts.strftime('%Y-%m-%d')
        except Exception:
            text = str(value)
            return text[:10]

    def _last_numeric(self, arr: Optional[np.ndarray]) -> Optional[float]:
        if arr is None or len(arr) == 0:
            return None
        value = arr[-1]
        if pd.isna(value):
            return None
        return float(value)

    def _json_number(self, value: Any, default: Any = None) -> Any:
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        try:
            number = float(value)
        except Exception:
            return default
        if not np.isfinite(number):
            return default
        return number

    def _clean_numeric_list(self, values: Optional[np.ndarray]) -> List[Any]:
        if values is None:
            return []
        return [self._json_number(v, None) for v in values.tolist()]

    def _normalize_list(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(',') if part.strip()]
        return [str(value).strip()]

    def _parse_concepts(self, raw: Any) -> List[str]:
        if raw in (None, ''):
            return []
        if isinstance(raw, list):
            return [str(v).strip() for v in raw if str(v).strip()]
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except Exception:
                pass
            for sep in ['|', ',', '，', ';', '、', '/']:
                if sep in text:
                    parts = [part.strip() for part in text.split(sep)]
                    return [part for part in parts if part]
            return [text]
        return [str(raw).strip()]

    def _parse_concept_tags(self, raw: Any) -> List[str]:
        return self._parse_concepts(raw)

    def _empty_search_result(self, request: Dict[str, Any], today: str, error: str = '') -> Dict[str, Any]:
        return {
            'items': [],
            'total': 0,
            'page': max(int(request.get('page') or 1), 1),
            'page_size': max(int(request.get('page_size') or 20), 1),
            'sort_by': str(request.get('sort_by') or 'change_pct'),
            'sort_order': str(request.get('sort_order') or 'desc'),
            'applied_formula': str(request.get('formula') or ''),
            'applied_template': None,
            'date': today,
            'error': error,
        }

    def _sort_search_items(self, items: List[Dict[str, Any]], sort_by: str, sort_order: str) -> List[Dict[str, Any]]:
        reverse = sort_order != 'asc'

        def _key(item: Dict[str, Any]):
            value = item.get(sort_by)
            if value is None:
                value = 0
            return value

        try:
            return sorted(items, key=_key, reverse=reverse)
        except Exception:
            return items
