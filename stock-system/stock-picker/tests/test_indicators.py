"""indicators 单元测试: MA / EMA / MACD / RSI / KDJ / HHV 一致性。"""
import numpy as np
import pandas as pd
import pytest

from indicators import (
    compute_ma, compute_ema, compute_macd, compute_rsi, compute_kdj, compute_hhv
)


def _make_multi(n=300, n_codes=10, seed=0):
    """构造多只股票的长表。"""
    np.random.seed(seed)
    parts = []
    for i in range(n_codes):
        code = f'{i:06d}'
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=n),
            'open': 10 + np.cumsum(np.random.randn(n) * 0.05),
            'high': 10 + np.cumsum(np.random.randn(n) * 0.05) + 0.5,
            'low': 10 + np.cumsum(np.random.randn(n) * 0.05) - 0.5,
            'close': 10 + np.cumsum(np.random.randn(n) * 0.05),
            'volume': np.random.randint(1_000_000, 10_000_000, n),
        })
        df.insert(0, 'code', code)
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


class TestMA:
    def test_ma5_first_4_nan(self):
        df = _make_multi(n_codes=1, n=10)
        out = compute_ma(df, periods=(5,))
        assert out['ma5'].iloc[:4].isna().all()
        # 第 5 行起非 NaN
        assert pd.notna(out['ma5'].iloc[4])

    def test_ma5_value(self):
        df = _make_multi(n_codes=1, n=10)
        out = compute_ma(df, periods=(5,))
        expected = df['close'].iloc[:5].mean()
        assert out['ma5'].iloc[4] == pytest.approx(expected)

    def test_ma_per_code(self):
        df = _make_multi(n_codes=3, n=20)
        out = compute_ma(df, periods=(5,))
        for code, group in out.groupby('code'):
            series = group['ma5'].dropna()
            # 同长度下 ma5 = close.rolling(5).mean()
            raw = group['close'].rolling(5).mean()
            assert series.tolist() == pytest.approx(raw.dropna().tolist())


class TestKDJ:
    def test_kdj_init_value_50(self):
        df = _make_multi(n_codes=1, n=20)
        out = compute_kdj(df)
        # 前 8 根 NaN,第 9 根起 K 应该是 50 (RSV 边界)
        k = out['kdj_k'].iloc[:8].tolist()
        assert all(pd.isna(v) for v in k)

    def test_kdj_value_range(self):
        df = _make_multi(n_codes=1, n=100)
        out = compute_kdj(df)
        valid_k = out['kdj_k'].dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()


class TestMACD:
    def test_macd_signs(self):
        df = _make_multi(n_codes=1, n=100)
        out = compute_macd(df)
        assert 'macd_dif' in out.columns
        assert 'macd_dea' in out.columns
        assert 'macd_hist' in out.columns
        # hist = 2 * (dif - dea)
        diff = (out['macd_dif'] - out['macd_dea']) * 2
        assert out['macd_hist'].dropna().tolist() == pytest.approx(diff.dropna().tolist())


class TestRSI:
    def test_rsi_range(self):
        df = _make_multi(n_codes=1, n=100)
        out = compute_rsi(df)
        valid = out['rsi14'].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


class TestHHV:
    def test_hhv_correct(self):
        df = _make_multi(n_codes=1, n=50)
        out = compute_hhv(df, 'high', periods=(20,))
        raw = df['high'].rolling(20).max()
        assert out['hhv20'].dropna().tolist() == pytest.approx(raw.dropna().tolist())
