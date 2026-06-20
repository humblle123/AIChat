"""向量化技术指标。一次性对全市场 DataFrame 算 MA/EMA/KDJ/HHV/REF 等。

调用约定:
  - 输入:  长表 DataFrame,列含 ['code', 'date', 'open', 'high', 'low', 'close', 'volume']
  - 输出:  按 'code' 分组聚合后的 DataFrame,带 ma5/ma10/ma20/ma60/ma120/ma250
          rsi14/macd_dif/macd_dea/macd_hist/kdj_k/kdj_d/kdj_j/hhv_n 等
  - 设计:  全部 groupby + rolling/ewm,无 Python for 循环
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _ensure_sorted(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(['code', 'date']).reset_index(drop=True)


def compute_ma(df: pd.DataFrame, periods=(5, 10, 20, 60, 120, 250)) -> pd.DataFrame:
    """对每只股票算各周期 MA,返回原表加 ma{period} 列。"""
    df = _ensure_sorted(df)
    g = df.groupby('code', sort=False)['close']
    for p in periods:
        df[f'ma{p}'] = g.transform(lambda s, p=p: s.rolling(p, min_periods=p).mean())
    return df


def compute_ema(df: pd.DataFrame, periods=(10, 12, 26)) -> pd.DataFrame:
    """对每只股票算各周期 EMA。"""
    df = _ensure_sorted(df)
    g = df.groupby('code', sort=False)['close']
    for p in periods:
        df[f'ema{p}'] = g.transform(lambda s, p=p: s.ewm(span=p, adjust=False).mean())
    return df


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD 指标 (12, 26, 9)。"""
    df = _ensure_sorted(df)
    g = df.groupby('code', sort=False)['close']
    ema_fast = g.transform(lambda s: s.ewm(span=fast, adjust=False).mean())
    ema_slow = g.transform(lambda s: s.ewm(span=slow, adjust=False).mean())
    df['macd_dif'] = ema_fast - ema_slow
    df['macd_dea'] = df.groupby('code', sort=False)['macd_dif'].transform(
        lambda s: s.ewm(span=signal, adjust=False).mean()
    )
    df['macd_hist'] = (df['macd_dif'] - df['macd_dea']) * 2
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """RSI(14)。"""
    df = _ensure_sorted(df)
    g = df.groupby('code', sort=False)['close']
    delta = g.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(df['code'], sort=False).transform(
        lambda s: s.ewm(alpha=1 / period, adjust=False).mean()
    )
    avg_loss = loss.groupby(df['code'], sort=False).transform(
        lambda s: s.ewm(alpha=1 / period, adjust=False).mean()
    )
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['rsi14'] = 100 - (100 / (1 + rs))
    return df


def compute_kdj(df: pd.DataFrame, n: int = 9, k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
    """KDJ(9, 3, 3)。

    K/D 是递归形式:  K[i] = (1-1/k_period) * K[i-1] + (1/k_period) * RSV[i],初值 50。
    pandas 没有跨行 state 的 transform,所以对每只股票用一次 groupby.apply 跑 O(n) 循环,
    比逐股 Python 循环(原来 5000 次外部循环)快,因为 groupby.apply 一次性分发到 C 级别。
    """
    df = _ensure_sorted(df)
    g = df.groupby('code', sort=False)

    # 9 日窗口的"高"取 max(high, close) 联合最高,"低"取 min(low, close) 联合最低
    # 否则 close 突破 9 日 high 时 RSV 会超 100,跌破 9 日 low 时 RSV 会为负
    eff_high = pd.concat([df['high'], df['close']], axis=1).max(axis=1)
    eff_low = pd.concat([df['low'], df['close']], axis=1).min(axis=1)
    g_h = eff_high.groupby(df['code'], sort=False)
    g_l = eff_low.groupby(df['code'], sort=False)
    high_n = g_h.transform(lambda s: s.rolling(n, min_periods=n).max())
    low_n = g_l.transform(lambda s: s.rolling(n, min_periods=n).min())
    rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    # 分母为 0 的情况用 50 代替(极少见)
    rsv = rsv.where(~((high_n - low_n) == 0), 50.0)

    alpha_k = 1.0 / k_period
    alpha_d = 1.0 / d_period

    def _sma_one_stock(group: pd.Series, alpha: float) -> pd.Series:
        result = np.empty(len(group), dtype=float)
        prev = 50.0
        arr = group.values
        for i in range(len(arr)):
            if np.isnan(arr[i]):
                result[i] = np.nan
                continue
            prev = (1 - alpha) * prev + alpha * arr[i]
            result[i] = prev
        return pd.Series(result, index=group.index)

    kdj_k = rsv.groupby(df['code'], sort=False).apply(lambda s: _sma_one_stock(s, alpha_k))
    if isinstance(kdj_k.index, pd.MultiIndex):
        kdj_k = kdj_k.reset_index(level=0, drop=True)
    kdj_d = kdj_k.groupby(df['code'], sort=False).apply(lambda s: _sma_one_stock(s, alpha_d))
    if isinstance(kdj_d.index, pd.MultiIndex):
        kdj_d = kdj_d.reset_index(level=0, drop=True)

    df['kdj_k'] = kdj_k.values
    df['kdj_d'] = kdj_d.values
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    return df


def compute_hhv(df: pd.DataFrame, col: str, periods=(50, 100, 250)) -> pd.DataFrame:
    """N 日 highest high。"""
    df = _ensure_sorted(df)
    g = df.groupby('code', sort=False)[col]
    for p in periods:
        df[f'hhv{p}'] = g.transform(lambda s, p=p: s.rolling(p, min_periods=p).max())
    return df


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """一次性算所有常用指标,加列。"""
    df = compute_ma(df)
    df = compute_ema(df)
    df = compute_macd(df)
    df = compute_rsi(df)
    df = compute_kdj(df)
    df = compute_hhv(df, 'high')
    return df


def latest_per_code(df: pd.DataFrame) -> pd.DataFrame:
    """每只股票取最后一行。"""
    return df.groupby('code', sort=False).tail(1).reset_index(drop=True)


def last_n_per_code(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """每只股票取最后 n 行,常用于策略条件需要窗口的情况。"""
    return df.groupby('code', sort=False).tail(n).reset_index(drop=True)
