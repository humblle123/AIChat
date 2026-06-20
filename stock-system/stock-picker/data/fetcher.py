"""腾讯财经数据抓取模块"""
import requests
import json
import time
import os
import hashlib
from typing import Any, List, Dict, Optional
from config import TENCENT_API
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://finance.qq.com/',
}

BASE_DIR = Path(__file__).resolve().parents[2]
LOCAL_TENCENT_HS_PATH = BASE_DIR / 'data' / 'tencent_hs.json'
DAILY_UPDATE_STATE_PATH = BASE_DIR / 'data' / 'daily_update_state.json'
REQUEST_TIMEOUT = 10
REQUEST_RETRIES = 3

_SESSION = None


def _get_session() -> requests.Session:
    """创建带重试的 HTTP session。"""
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    session = requests.Session()
    retry = Retry(
        total=REQUEST_RETRIES,
        connect=REQUEST_RETRIES,
        read=REQUEST_RETRIES,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET']),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    _SESSION = session
    return session


def _request_text(url: str, params: Optional[Dict] = None, encoding: str = 'utf-8') -> Optional[str]:
    """带重试的文本请求。"""
    try:
        resp = _get_session().get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.encoding = encoding
        return resp.text
    except Exception as e:
        print(f"[Fetcher] 请求失败: {url} - {e}")
        return None


def _fingerprint_codes(codes: List[str]) -> str:
    """为股票池生成稳定指纹，避免错用旧进度。"""
    payload = '\n'.join(_normalize_code_list(codes))
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def _normalize_code_list(codes: List[str]) -> List[str]:
    """统一股票代码格式，去重并保留顺序。"""
    normalized = []
    seen = set()
    for code in codes:
        if code in (None, ''):
            continue
        text = str(code).strip()
        if not text:
            continue
        if text.lower().startswith(('sh', 'sz', 'bj')) and len(text) >= 8:
            text = text[2:]
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _load_daily_update_state(job_key: str) -> Dict[str, Any]:
    """读取日线更新断点状态。"""
    if not DAILY_UPDATE_STATE_PATH.exists():
        return {}
    try:
        with DAILY_UPDATE_STATE_PATH.open('r', encoding='utf-8') as f:
            state = json.load(f)
        if state.get('job_key') != job_key:
            return {}
        return state if isinstance(state, dict) else {}
    except Exception as e:
        print(f"[Fetcher] 读取更新状态失败: {e}")
        return {}


def _save_daily_update_state(state: Dict[str, Any]) -> None:
    """保存日线更新断点状态。"""
    DAILY_UPDATE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DAILY_UPDATE_STATE_PATH.with_suffix('.tmp')
    with tmp_path.open('w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, DAILY_UPDATE_STATE_PATH)


def _clear_daily_update_state() -> None:
    """清理断点状态。"""
    try:
        if DAILY_UPDATE_STATE_PATH.exists():
            DAILY_UPDATE_STATE_PATH.unlink()
    except Exception as e:
        print(f"[Fetcher] 清理更新状态失败: {e}")


def _safe_float(value, default: float = 0.0) -> float:
    """尽量从腾讯接口的混合结构里提取数值。"""
    if value in (None, ''):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(',', '').strip()
        if not cleaned:
            return default
        return float(cleaned)
    if isinstance(value, dict):
        for key in ('value', 'amount', 'price', 'close', 'open', 'high', 'low'):
            if key in value:
                return _safe_float(value.get(key), default)
        return default
    if isinstance(value, (list, tuple)):
        for item in value:
            try:
                return _safe_float(item, default)
            except (TypeError, ValueError):
                continue
        return default
    return float(value)


def _safe_int(value, default: int = 0) -> int:
    if value in (None, ''):
        return default
    return int(_safe_float(value, float(default)))


def _infer_market(code: str) -> str:
    """根据代码前缀推断市场。"""
    if code.startswith('sh688'):
        return 'KCB'
    if code.startswith('sh6') or code.startswith('sh5'):
        return 'SHA'
    if code.startswith('sz300') or code.startswith('sz301'):
        return 'CYB'
    if code.startswith('sz000') or code.startswith('sz001') or code.startswith('sz002') or code.startswith('sz003'):
        return 'SZA'
    return ''


def _is_excluded_security(name: str) -> bool:
    """判断是否应排除在股票池之外。"""
    if not name:
        return False
    blacklist = ['ETF', '基金', '债', '可转债', '转债', '退市']
    return any(token in name for token in blacklist)


def load_tencent_hs_list(path: str | os.PathLike | None = None) -> Dict[str, str]:
    """加载本地缓存的腾讯 A 股列表。"""
    file_path = Path(path) if path else LOCAL_TENCENT_HS_PATH
    if not file_path.exists():
        return {}
    try:
        with file_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(code): str(name) for code, name in data.items()}
    except Exception as e:
        print(f"[Fetcher] 读取本地股票池失败: {e}")
    return {}


def sync_stock_basic_from_local_cache(path: str | os.PathLike | None = None) -> int:
    """
    将本地缓存的腾讯 A 股列表同步到 stock_basic。

    规则：
    - 以 data/tencent_hs.json 为主来源
    - 保留数据库中已有的行业、概念、上市日期等扩展字段
    - 默认排除退市、ETF、债券类标的
    """
    from data.store import get_stocks, save_stock_basic

    cached = load_tencent_hs_list(path)
    if not cached:
        print("[Fetcher] 本地股票池为空，跳过 stock_basic 同步")
        return 0

    existing = get_stocks()
    existing_map: Dict[str, Dict] = {}
    if existing is not None and not existing.empty:
        for _, row in existing.iterrows():
            existing_map[str(row['code'])] = row.to_dict()

    records = []
    for raw_code, raw_name in cached.items():
        code = raw_code[-6:] if len(raw_code) >= 6 else raw_code
        name = str(raw_name).strip()

        if _is_excluded_security(name):
            continue

        prev = existing_map.get(code, {})
        market = _infer_market(raw_code) or _infer_market(code) or prev.get('market', '')
        concept_tags = prev.get('concept_tags', '[]')
        listed_date = prev.get('listed_date') or prev.get('list_date')
        records.append({
            'code': code,
            'name': name or prev.get('name', code),
            'market': market,
            'industry': prev.get('industry', ''),
            'concept_tags': concept_tags,
            'security_type': 'stock',
            'listed_date': listed_date,
            'is_delisted': 0,
            'is_st': 1 if ('ST' in name or '*ST' in name) else int(prev.get('is_st', 0) or 0),
            'is_suspended': int(prev.get('is_suspended', 0) or 0),
        })

    if not records:
        print("[Fetcher] 没有可同步的股票基础信息")
        return 0

    save_stock_basic(records)
    print(f"[Fetcher] 同步 stock_basic 完成: {len(records)} 只")
    return len(records)


def get_quote(codes: List[str]) -> List[Dict]:
    """
    获取实时行情
    腾讯接口返回格式: v_pv1Detail = ["股票代码", "名称", "代码", "现价", "昨收", "今开", "成交量(手)", 
                                    "外盘", "内盘", "买入", "卖出", "换手率", "市盈率", ...]
    """
    if not codes:
        return []
    
    results = []
    # 每批次最多50个
    batch_size = 50
    
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        codes_str = ','.join([f'sh{c}' if c.startswith(('6', '5')) else f'sz{c}' for c in batch])
        url = TENCENT_API['quote'] + codes_str

        text = _request_text(url, encoding='gbk')
        if not text:
            time.sleep(0.2)
            continue

        for line in text.strip().split('\n'):
            if '=' not in line:
                continue
            code_part, data_part = line.split('=', 1)
            try:
                data = json.loads(data_part)
                if 'data' not in data:
                    continue
                
                stock_data = data['data']
                if isinstance(stock_data, dict):
                    for code, info in stock_data.items():
                        if isinstance(info, dict):
                            results.append({
                                'code': info.get('code', code),
                                'name': info.get('name', ''),
                                'price': float(info.get('price', 0)),
                                'close': float(info.get('close', 0)),  # 昨收
                                'open': float(info.get('open', 0)),
                                'volume': int(info.get('volume', 0)),
                                'amount': float(info.get('amount', 0)),
                                'bid1': float(info.get('bid1', 0)),
                                'ask1': float(info.get('ask1', 0)),
                                'pe': float(info.get('pe', 0)) if info.get('pe') else None,
                                'pb': float(info.get('pb', 0)) if info.get('pb') else None,
                                'total_mv': float(info.get('mktcap', 0)),
                                'circ_mv': float(info.get('nmc', 0)) if info.get('nmc') else float(info.get('mktcap', 0)),
                                'up': float(info.get('updown', 0)),
                            })
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        time.sleep(0.2)  # 避免请求过快
    
    return results


def get_kline(code: str, period: str = 'day', count: int = 600) -> Optional[pd.DataFrame]:
    """
    获取 K 线数据
    period: day/week/month
    count: 获取数量
    """
    market = 'sh' if code.startswith(('6', '5')) else 'sz'
    url = TENCENT_API['kline']
    params = {
        '_var': 'kline_dayqfq',
        'param': f'{market}{code},day,,,{count},qfq'
    }
    
    try:
        text = _request_text(url, params=params, encoding='utf-8')
        if not text:
            return None
        
        # 解析返回数据
        # 格式: var kline_dayqfq={...}
        if '=' not in text:
            return None
        
        json_str = text.split('=', 1)[1]
        data = json.loads(json_str)
        
        if 'data' not in data or not data['data']:
            return None

        market_code = f'{market}{code}'
        block = data['data'].get(market_code) or data['data'].get(code, {})
        day_data = (
            block.get('day')
            or block.get('qfqday')
            or block.get('hfqday')
            or data['data'].get('day')
        )
        if not day_data:
            return None

        records = []
        for item in day_data:
            if isinstance(item, dict):
                records.append({
                    'date': item.get('date') or item.get('time'),
                    'open': _safe_float(item.get('open')),
                    'close': _safe_float(item.get('close')),
                    'high': _safe_float(item.get('high')),
                    'low': _safe_float(item.get('low')),
                    'volume': _safe_int(item.get('volume')),
                    'amount': _safe_float(item.get('amount')),
                    'pre_close': _safe_float(item.get('pre_close'), None),
                })
                continue

            if len(item) >= 6:
                open_price = _safe_float(item[1])
                close_price = _safe_float(item[2])
                high_price = _safe_float(item[3])
                low_price = _safe_float(item[4])
                volume_lots = _safe_int(item[5]) if len(item) > 5 else 0
                volume_shares = volume_lots * 100  # API 返回手，转为股
                
                # 优先用 API 返回的 amount，否则用均价 × 成交量估算
                amount = _safe_float(item[6]) if len(item) > 6 else 0.0
                if amount == 0.0 and volume_shares > 0:
                    avg_price = (open_price + close_price + high_price + low_price) / 4
                    amount = round(avg_price * volume_shares, 2)
                
                records.append({
                    'date': item[0],
                    'open': open_price,
                    'close': close_price,
                    'high': high_price,
                    'low': low_price,
                    'volume': volume_shares,
                    'amount': amount,
                    'pre_close': _safe_float(item[7], None) if len(item) > 7 else None,
                })
        
        if not records:
            return None
        
        df = pd.DataFrame(records)
        df = df[df['date'].notna()].copy()
        if df.empty:
            return None
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df[df['date'].notna()].copy()
        if df.empty:
            return None
        
        # 计算涨跌幅
        if 'pre_close' not in df.columns or df['pre_close'].isna().all():
            df['pre_close'] = df['close'].shift(1)
        else:
            df['pre_close'] = df['pre_close'].fillna(df['close'].shift(1))
        df['up'] = ((df['close'] - df['pre_close']) / df['pre_close']) * 100
        df['up'] = df['up'].replace([float('inf'), float('-inf')], pd.NA).fillna(0)
        
        return df
        
    except Exception as e:
        print(f"[Fetcher] 获取K线失败 {code}: {e}")
        return None


def get_all_stock_codes() -> List[str]:
    """获取所有 A 股股票代码"""
    # 简化的股票列表，实际应该从数据源获取
    # 这里返回一个模拟列表
    codes = []
    
    # 沪市主板
    for i in range(600000, 602000):
        codes.append(str(i))
    
    # 科创板
    for i in range(688000, 688800):
        codes.append(str(i))
    
    # 深市主板
    for i in range(1, 3000):
        codes.append(str(i).zfill(6))
    
    # 创业板
    for i in range(300001, 301000):
        codes.append(str(i).zfill(6))
    
    return codes


def batch_update_daily_data(codes: List[str], days: int = 1, resume: bool = True, max_workers: int = 8) -> int:
    """
    批量更新日线数据(并发版),返回更新的股票数量。

    max_workers: 并发线程数(腾讯接口限流,建议 4-10)。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    normalized_codes = _normalize_code_list(codes)
    if not normalized_codes:
        return 0

    job_key = _fingerprint_codes(normalized_codes)
    state = _load_daily_update_state(job_key) if resume else {}
    start_index = int(state.get('next_index', 0) or 0)
    updated = int(state.get('updated', 0) or 0)
    failed = int(state.get('failed', 0) or 0)
    if start_index >= len(normalized_codes):
        start_index = 0
        updated = 0
        failed = 0

    from data.store import save_daily_data

    target = normalized_codes[start_index:]

    def _fetch_one(code: str) -> tuple:
        df = None
        for attempt in range(1, REQUEST_RETRIES + 1):
            df = get_kline(code, count=days)
            if df is not None and not df.empty:
                break
            if attempt < REQUEST_RETRIES:
                time.sleep(0.5 * attempt)
        if df is not None and not df.empty:
            save_daily_data(code, df.to_dict('records'))
            return (code, True)
        return (code, False)

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, code): code for code in target}
        for fut in as_completed(futures):
            code, ok = fut.result()
            completed += 1
            if ok:
                updated += 1
            else:
                failed += 1
            if completed % 100 == 0:
                from logger import get_logger
                get_logger(__name__).info(f"日线进度 {completed}/{len(target)}")
            # 断点续跑进度
            _save_daily_update_state({
                'job_key': job_key,
                'next_index': start_index + completed,
                'updated': updated,
                'failed': failed,
                'total': len(normalized_codes),
                'days': days,
                'updated_at': datetime.now().isoformat(timespec='seconds'),
            })

    from logger import get_logger
    get_logger(__name__).info(f"日线批量更新完成: 成功 {updated} 只, 失败 {failed} 只")
    _clear_daily_update_state()
    return updated


if __name__ == '__main__':
    # 测试
    codes = ['600519', '000858', '300750']
    quotes = get_quote(codes)
    print(f"获取到 {len(quotes)} 条行情数据")
    
    kline = get_kline('600519')
    if kline is not None:
        print(f"K线数据: {len(kline)} 条")
        print(kline.tail())
