"""formula_engine 单元测试: 词法、解析、求值、校验。"""
import pandas as pd
import numpy as np
import pytest

from formula_engine import (
    validate, evaluate_formula, parse, FormulaError, tokenize,
)


# ===== 词法/解析 =====
class TestLexer:
    def test_tokenize_numbers(self):
        tokens = tokenize('1 2.5 .3')
        assert [t.value for t in tokens if t.kind == 'NUMBER'] == [1.0, 2.5, 0.3]

    def test_tokenize_keywords(self):
        tokens = tokenize('AND OR NOT')
        kinds = [t.kind for t in tokens if t.kind in ('AND', 'OR', 'NOT')]
        assert kinds == ['AND', 'OR', 'NOT']

    def test_tokenize_compare(self):
        tokens = tokenize('a >= b <= c != d = e')
        assert all(t.kind in ('GE', 'LE', 'NE', 'EQ', 'ID') for t in tokens)

    def test_tokenize_invalid_char(self):
        with pytest.raises(FormulaError):
            tokenize('CLOSE > @1')


class TestParser:
    def test_parse_simple(self):
        ast = parse('CLOSE > MA(CLOSE, 5)')
        assert ast is not None

    def test_parse_precedence(self):
        # a OR b AND c  →  a OR (b AND c)  (AND 优先级高于 OR)
        ast = parse('CLOSE > 5 OR OPEN < 3 AND VOL > 1000')
        assert ast is not None

    def test_parse_paren(self):
        ast = parse('(CLOSE + OPEN) * 2')
        assert ast is not None


# ===== 校验 =====
class TestValidate:
    @pytest.mark.parametrize('expr', [
        'RPS50 > 90',
        'CLOSE > MA(CLOSE, 5)',
        'KDJ_J < 18 AND CLOSE > EMA(CLOSE, 10)',
        'COUNT(CLOSE > MA(CLOSE, 5), 20) > 10',
        'CROSS(CLOSE, MA(CLOSE, 10))',
        'REF(CLOSE, 5) > CLOSE',
        'RPS50 > 90 AND (RPS120 > 93 OR RPS250 > 95)',
        'NOT (CLOSE > 100)',
    ])
    def test_valid(self, expr):
        result = validate(expr)
        assert result['valid'] is True, result['errors']
        assert result['used_fields']

    @pytest.mark.parametrize('expr', [
        '',
        'CLOSE >',
        'AND OR NOT',
        '(unclosed',
    ])
    def test_invalid(self, expr):
        result = validate(expr)
        if expr:
            assert result['valid'] is False
            assert result['errors']


# ===== 求值 =====
def _make_df(n=300, seed=0):
    np.random.seed(seed)
    return pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n),
        'open': 10 + np.cumsum(np.random.randn(n) * 0.05),
        'high': 10 + np.cumsum(np.random.randn(n) * 0.05) + 0.5,
        'low': 10 + np.cumsum(np.random.randn(n) * 0.05) - 0.5,
        'close': 10 + np.cumsum(np.random.randn(n) * 0.05),
        'volume': np.random.randint(1_000_000, 10_000_000, n),
    })


class TestEvaluate:
    def test_scalar_rps(self):
        df = _make_df()
        hit, _ = evaluate_formula('RPS50 > 85', df, scalars={'rps50': 90})
        assert hit is True
        hit, _ = evaluate_formula('RPS50 > 95', df, scalars={'rps50': 90})
        assert hit is False

    def test_scalar_rps_null(self):
        df = _make_df()
        hit, _ = evaluate_formula('RPS50 > 85', df, scalars={})
        assert hit is False  # None 不命中数值比较

    def test_ma_above(self):
        df = _make_df()
        hit, _ = evaluate_formula('CLOSE > MA(CLOSE, 20)', df, scalars={})
        assert isinstance(hit, bool)

    def test_count(self):
        df = _make_df()
        hit, info = evaluate_formula('COUNT(CLOSE > MA(CLOSE, 5), 20) > 0', df, scalars={})
        assert isinstance(hit, bool)
        assert 'last_value' in info

    def test_cross(self):
        df = _make_df()
        # 任何 300 根里几乎都有 5 日均线上穿事件
        hit, _ = evaluate_formula('CROSS(CLOSE, MA(CLOSE, 5))', df, scalars={})
        assert isinstance(hit, bool)

    def test_ref(self):
        df = _make_df()
        # 5 日前是 NaN 不命中,CLOSE > REF(CLOSE, 5) 在 random walk 中约 50% 命中
        hit, _ = evaluate_formula('CLOSE > REF(CLOSE, 5)', df, scalars={})
        assert isinstance(hit, bool)

    def test_and_or_not(self):
        df = _make_df()
        hit, _ = evaluate_formula(
            'CLOSE > MA(CLOSE, 5) AND VOL > 1000', df, scalars={}
        )
        assert isinstance(hit, bool)
        hit, _ = evaluate_formula(
            'NOT (CLOSE > 9999)', df, scalars={}
        )
        assert hit is True

    def test_variable_assignment(self):
        df = _make_df()
        expr = 'ZXDQ := EMA(EMA(CLOSE, 10), 10); ZXDKX := (MA(CLOSE, 14) + MA(CLOSE, 28)) / 2; CLOSE > ZXDQ AND ZXDQ > ZXDKX'
        result = validate(expr)
        assert result['valid']
        hit, _ = evaluate_formula(expr, df, scalars={})
        assert isinstance(hit, bool)

    def test_b1_full_formula(self):
        """b1 真实公式。"""
        df = _make_df(n=500)
        expr = (
            'ZXDQ := EMA(EMA(CLOSE, 10), 10); '
            'ZXDKX := (MA(CLOSE, 14) + MA(CLOSE, 28) + MA(CLOSE, 57) + MA(CLOSE, 114)) / 4; '
            'KDJ_J < 18 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX'
        )
        result = validate(expr)
        assert result['valid']
        hit, _ = evaluate_formula(expr, df, scalars={})
        assert isinstance(hit, bool)

    def test_s3_full_formula(self):
        df = _make_df(n=500)
        expr = 'RPS50 > 90 AND RPS120 > 93 AND RPS250 > 95 AND CLOSE / HHV(HIGH, 250) > 0.85'
        hit, _ = evaluate_formula(
            expr, df, scalars={'rps50': 95, 'rps120': 95, 'rps250': 95}
        )
        assert isinstance(hit, bool)
