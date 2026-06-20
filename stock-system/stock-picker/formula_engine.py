"""类通达信公式解析器与求值器。

支持的语法 (对齐 REQUIREMENTS.md 6.3):
  - 逻辑运算: AND OR NOT
  - 比较运算: > >= < <= = !=
  - 算术运算: + - * /
  - 括号
  - 函数: MA / EMA / REF / COUNT / HHV / LLV / CROSS
  - 字段别名: CLOSE/OPEN/HIGH/LOW/VOL  映射到 close/open/high/low/volume;
             KDJ_K/KDJ_D/KDJ_J  ->  kdj_k/kdj_d/kdj_j
             RPS50/RPS120/RPS250  ->  rps50/rps120/rps250
  - 自定义变量: 公式中可有 name := expr,后续 name 引用 expr 的结果

设计:
  - lexer -> 词法
  - parser -> AST
  - 整段公式求值: 一组 RPS/行情快照输入(每个股票一行),得到命中布尔数组
  - 业务层负责把"对单股的指标序列" 喂进来 (KDJ/MA/EMA/HHV/LLV 等)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ===== 字段别名 =====

FIELD_ALIASES: Dict[str, str] = {
    'CLOSE': 'close', 'OPEN': 'open', 'HIGH': 'high', 'LOW': 'low', 'VOL': 'volume',
    'KDJ_K': 'kdj_k', 'KDJ_D': 'kdj_d', 'KDJ_J': 'kdj_j',
    'RPS50': 'rps50', 'RPS120': 'rps120', 'RPS250': 'rps250',
    'RPS5': 'rps5', 'RPS10': 'rps10', 'RPS15': 'rps15', 'RPS20': 'rps20',
    'PE_TTM': 'pe_ttm', 'PB': 'pb', 'ROE_TTM': 'roe_ttm',
    'TURNOVER_RATE': 'turnover_rate', 'VOLUME_RATIO_1D': 'volume_ratio_1d',
    'MA5': 'ma5', 'MA10': 'ma10', 'MA20': 'ma20', 'MA60': 'ma60',
    'MA120': 'ma120', 'MA250': 'ma250',
    'RSI14': 'rsi14', 'MACD_DIF': 'macd_dif', 'MACD_DEA': 'macd_dea', 'MACD_HIST': 'macd_hist',
}


# ===== 词法 =====

TOKEN_REGEX = re.compile(
    r"""
    \s+                                    |   # 空白
    (?P<NUMBER>\d+\.\d+|\.\d+|\d+)         |
    (?P<AND>AND\b)                          |
    (?P<OR>OR\b)                            |
    (?P<NOT>NOT\b)                          |
    (?P<ASSIGN>:=)                          |
    (?P<LE><=)                              |
    (?P<GE>>=)                              |
    (?P<NE>!=)                              |
    (?P<LT><)                               |
    (?P<GT>>)                               |
    (?P<EQ>=)                               |
    (?P<LPAREN>\()                          |
    (?P<RPAREN>\))                          |
    (?P<COMMA>,)                            |
    (?P<SEMI>;)                             |
    (?P<OP>[+\-*/])                         |
    (?P<ID>[A-Za-z_][A-Za-z_0-9]*)
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    kind: str
    value: Any
    pos: int


def tokenize(src: str) -> List[Token]:
    tokens: List[Token] = []
    pos = 0
    while pos < len(src):
        m = TOKEN_REGEX.match(src, pos)
        if not m:
            raise FormulaError(f'无法识别的字符: {src[pos]!r} (位置 {pos})')
        pos = m.end()
        for kind, value in m.groupdict().items():
            if value is not None:
                if kind == 'NUMBER':
                    tokens.append(Token('NUMBER', float(value), pos))
                else:
                    tokens.append(Token(kind, value, pos))
                break
    return tokens


# ===== AST =====

@dataclass
class Node:
    pass


@dataclass
class NumberLit(Node):
    value: float


@dataclass
class FieldRef(Node):
    name: str  # 已经是小写别名


@dataclass
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass
class UnaryOp(Node):
    op: str
    operand: Node


@dataclass
class FuncCall(Node):
    name: str
    args: List[Node]


@dataclass
class VarAssign(Node):
    name: str
    value: Node


@dataclass
class StmtList(Node):
    stmts: List[Node]
    final: Node


class FormulaError(Exception):
    pass


# ===== 解析 =====

class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset: int = 0) -> Optional[Token]:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def consume(self, kind: Optional[str] = None) -> Token:
        if self.pos >= len(self.tokens):
            if kind:
                raise FormulaError(f'公式意外结束,期望 {kind}')
            raise FormulaError('公式意外结束')
        tok = self.tokens[self.pos]
        if kind and tok.kind != kind:
            raise FormulaError(f'期望 {kind},遇到 {tok.kind} ({tok.value!r})')
        self.pos += 1
        return tok

    # grammar:
    #   program    := stmt_list
    #   stmt_list  := (assign ';')* expr
    #   assign     := ID ':=' expr
    #   expr       := or_expr
    #   or_expr    := and_expr (OR and_expr)*
    #   and_expr   := not_expr (AND not_expr)*
    #   not_expr   := NOT not_expr | cmp_expr
    #   cmp_expr   := add_expr ((<=|>=|!=|=|<|>) add_expr)?
    #   add_expr   := mul_expr (('+'|'-') mul_expr)*
    #   mul_expr   := unary (('*'|'/') unary)*
    #   unary      := '-' unary | primary
    #   primary    := NUMBER | ID | ID '(' args ')' | '(' expr ')'
    #   args       := expr (',' expr)*

    def parse(self) -> Node:
        stmts: List[Node] = []
        while True:
            save = self.pos
            try:
                assign = self.parse_assign()
            except FormulaError:
                self.pos = save
                break
            stmts.append(assign)
            if self.peek() and self.peek().kind == 'SEMI':
                self.consume('SEMI')
            else:
                break
        if not stmts:
            return self.parse_expr()
        final = self.parse_expr()
        return StmtList(stmts, final)

    def parse_assign(self) -> Node:
        tok = self.peek()
        if not tok or tok.kind != 'ID':
            raise FormulaError('expected ID at assign')
        name = tok.value
        save = self.pos
        self.consume('ID')
        nxt = self.peek()
        if nxt and nxt.kind == 'ASSIGN':
            self.consume('ASSIGN')
            value = self.parse_expr()
            return VarAssign(name, value)
        self.pos = save
        raise FormulaError('not an assign')

    def parse_expr(self) -> Node:
        return self.parse_or()

    def parse_or(self) -> Node:
        left = self.parse_and()
        while self.peek() and self.peek().kind == 'OR':
            self.consume()
            right = self.parse_and()
            left = BinOp('OR', left, right)
        return left

    def parse_and(self) -> Node:
        left = self.parse_not()
        while self.peek() and self.peek().kind == 'AND':
            self.consume()
            right = self.parse_not()
            left = BinOp('AND', left, right)
        return left

    def parse_not(self) -> Node:
        if self.peek() and self.peek().kind == 'NOT':
            self.consume()
            return UnaryOp('NOT', self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self) -> Node:
        left = self.parse_add()
        op_tok = self.peek()
        if op_tok and op_tok.kind in ('LE', 'GE', 'NE', 'LT', 'GT', 'EQ'):
            self.consume()
            right = self.parse_add()
            return BinOp(op_tok.kind, left, right)
        return left

    def parse_add(self) -> Node:
        left = self.parse_mul()
        while self.peek() and self.peek().kind in ('OP',) and self.peek().value in ('+', '-'):
            op = self.consume().value
            right = self.parse_mul()
            left = BinOp(op, left, right)
        return left

    def parse_mul(self) -> Node:
        left = self.parse_unary()
        while self.peek() and self.peek().kind == 'OP' and self.peek().value in ('*', '/'):
            op = self.consume().value
            right = self.parse_unary()
            left = BinOp(op, left, right)
        return left

    def parse_unary(self) -> Node:
        if self.peek() and self.peek().kind == 'OP' and self.peek().value == '-':
            self.consume()
            return UnaryOp('-', self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Node:
        tok = self.peek()
        if not tok:
            raise FormulaError('unexpected end')
        if tok.kind == 'NUMBER':
            self.consume()
            return NumberLit(tok.value)
        if tok.kind == 'LPAREN':
            self.consume()
            node = self.parse_expr()
            self.consume('RPAREN')
            return node
        if tok.kind == 'ID':
            self.consume()
            if self.peek() and self.peek().kind == 'LPAREN':
                self.consume('LPAREN')
                args: List[Node] = []
                if not (self.peek() and self.peek().kind == 'RPAREN'):
                    args.append(self.parse_expr())
                    while self.peek() and self.peek().kind == 'COMMA':
                        self.consume()
                        args.append(self.parse_expr())
                self.consume('RPAREN')
                return FuncCall(tok.value, args)
            return FieldRef(tok.value)
        raise FormulaError(f'意外的 token: {tok.kind} ({tok.value!r})')


# ===== 求值 =====

class Evaluator:
    """对单只股票的一段历史数据求值,得到最终布尔。

    ctx 字段:
      - 'series': dict[str, np.ndarray]  序列数据(close/high/low/volume/kdj_k/...)
      - 'scalars': dict[str, float]      标量字段(pe_ttm/pb/rps50/...)
    """

    def __init__(self, ast: Node) -> None:
        self.ast = ast

    def eval(self, ctx: Dict[str, Any]) -> Any:
        return self._eval(self.ast, ctx)

    def _eval(self, node: Node, ctx: Dict[str, Any]) -> Any:
        if isinstance(node, NumberLit):
            return node.value
        if isinstance(node, FieldRef):
            return self._field(node.name, ctx)
        if isinstance(node, BinOp):
            return self._binop(node, ctx)
        if isinstance(node, UnaryOp):
            return self._unary(node, ctx)
        if isinstance(node, FuncCall):
            return self._func(node, ctx)
        if isinstance(node, VarAssign):
            return self._assign(node, ctx)
        if isinstance(node, StmtList):
            return self._stmt_list(node, ctx)
        raise FormulaError(f'未知 AST 节点: {type(node).__name__}')

    def _field(self, raw_name: str, ctx: Dict[str, Any]) -> Any:
        # 用户自定义变量优先
        if raw_name in ctx.get('locals', {}):
            return ctx['locals'][raw_name]
        key = FIELD_ALIASES.get(raw_name.upper(), raw_name.lower())
        if key in ctx.get('locals', {}):
            return ctx['locals'][key]
        if key in ctx.get('scalars', {}):
            return ctx['scalars'][key]
        if key in ctx.get('series', {}):
            return ctx['series'][key]
        # 标量 / 序列都没声明,返回 NaN 占位
        return np.nan

    def _binop(self, node: BinOp, ctx: Dict[str, Any]) -> Any:
        l = self._eval(node.left, ctx)
        r = self._eval(node.right, ctx)
        op = node.op
        try:
            if op == 'AND':
                if isinstance(l, (bool, np.bool_)) and isinstance(r, (bool, np.bool_)):
                    return bool(l) and bool(r)
                return _truthy(l) and _truthy(r)
            if op == 'OR':
                if isinstance(l, (bool, np.bool_)) and isinstance(r, (bool, np.bool_)):
                    return bool(l) or bool(r)
                return _truthy(l) or _truthy(r)
            if op in ('LE', 'GE', 'NE', 'LT', 'GT', 'EQ'):
                return _compare(op, l, r)
            if op == '+':
                return _safe_arith(l, r, lambda a, b: a + b)
            if op == '-':
                return _safe_arith(l, r, lambda a, b: a - b)
            if op == '*':
                return _safe_arith(l, r, lambda a, b: a * b)
            if op == '/':
                return _safe_arith(l, r, lambda a, b: a / b)
        except FormulaError:
            raise
        except Exception as e:
            raise FormulaError(f'运算失败 {op}: {e}')
        raise FormulaError(f'不支持的二元运算: {op}')

    def _unary(self, node: UnaryOp, ctx: Dict[str, Any]) -> Any:
        v = self._eval(node.operand, ctx)
        if node.op == 'NOT':
            return not _truthy(v)
        if node.op == '-':
            if isinstance(v, np.ndarray):
                return -v
            return -v
        raise FormulaError(f'不支持的一元运算: {node.op}')

    def _func(self, node: FuncCall, ctx: Dict[str, Any]) -> Any:
        name = node.name.upper()
        args = [self._eval(a, ctx) for a in node.args]
        if name == 'MA':
            return _series_fn(args, lambda s, n: pd.Series(s).rolling(int(n), min_periods=1).mean().values)
        if name == 'EMA':
            return _series_fn(args, lambda s, n: pd.Series(s).ewm(span=int(n), adjust=False).mean().values)
        if name == 'REF':
            # REF(X, N) = N 日前的 X
            return _series_fn(args, lambda s, n: _ref(s, int(n)))
        if name == 'HHV':
            return _series_fn(args, lambda s, n: pd.Series(s).rolling(int(n), min_periods=1).max().values)
        if name == 'LLV':
            return _series_fn(args, lambda s, n: pd.Series(s).rolling(int(n), min_periods=1).min().values)
        if name == 'COUNT':
            # COUNT(X, N) = 过去 N 日 X 为真的天数 (X 是布尔数组)
            return _count(args)
        if name == 'CROSS':
            return _cross(args)
        raise FormulaError(f'不支持的函数: {node.name}')

    def _assign(self, node: VarAssign, ctx: Dict[str, Any]) -> Any:
        v = self._eval(node.value, ctx)
        ctx['locals'][node.name] = v
        return v

    def _stmt_list(self, node: StmtList, ctx: Dict[str, Any]) -> Any:
        for s in node.stmts:
            self._eval(s, ctx)
        return self._eval(node.final, ctx)


# ===== 辅助 =====

def _truthy(v: Any) -> bool:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        return not (np.isnan(v) or v == 0)
    if isinstance(v, np.ndarray):
        if v.size == 0:
            return False
        return bool(np.any(v))
    return bool(v)


def _compare(op: str, l: Any, r: Any) -> Any:
    if isinstance(l, np.ndarray) or isinstance(r, np.ndarray):
        ls, rs = np.asarray(l, dtype=float), np.asarray(r, dtype=float)
        if op == 'LE':
            return ls <= rs
        if op == 'GE':
            return ls >= rs
        if op == 'LT':
            return ls < rs
        if op == 'GT':
            return ls > rs
        if op == 'EQ':
            return ls == rs
        if op == 'NE':
            return ls != rs
    # 标量
    if l is None or r is None:
        return False
    try:
        if any(np.isnan(x) for x in (l, r) if isinstance(x, float)):
            return False
    except TypeError:
        pass
    if op == 'LE':
        return l <= r
    if op == 'GE':
        return l >= r
    if op == 'LT':
        return l < r
    if op == 'GT':
        return l > r
    if op == 'EQ':
        return l == r
    if op == 'NE':
        return l != r
    raise FormulaError(f'未知比较符: {op}')


def _safe_arith(l: Any, r: Any, fn: Callable[[float, float], float]) -> Any:
    if isinstance(l, np.ndarray) or isinstance(r, np.ndarray):
        ls = np.asarray(l, dtype=float)
        rs = np.asarray(r, dtype=float)
        with np.errstate(invalid='ignore', divide='ignore'):
            return fn(ls, rs)
    return fn(float(l), float(r))


def _series_fn(args: List[Any], fn: Callable[[np.ndarray, float], np.ndarray]) -> np.ndarray:
    if len(args) != 2:
        raise FormulaError('需要 2 个参数')
    s, n = args
    if not isinstance(n, (int, float)) or n <= 0:
        raise FormulaError(f'周期参数必须为正数,得到 {n!r}')
    s_arr = np.asarray(s, dtype=float)
    if s_arr.ndim == 0:
        s_arr = np.array([float(s_arr)])
    return fn(s_arr, float(n))


def _ref(s: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(s, np.nan, dtype=float)
    if n < len(s):
        out[n:] = s[:-n] if n > 0 else s
    return out


def _count(args: List[Any]) -> np.ndarray:
    if len(args) != 2:
        raise FormulaError('COUNT 需要 2 个参数')
    cond, n = args
    cond_arr = np.asarray(cond, dtype=bool)
    n = int(n)
    # 滚动求和: 过去 n 日(含今日)中为真的天数
    s = pd.Series(cond_arr.astype(int)).rolling(n, min_periods=1).sum()
    return s.values


def _cross(args: List[Any]) -> np.ndarray:
    if len(args) != 2:
        raise FormulaError('CROSS 需要 2 个参数')
    a, b = np.asarray(args[0], dtype=float), np.asarray(args[1], dtype=float)
    prev_a = np.concatenate([[np.nan], a[:-1]])
    prev_b = np.concatenate([[np.nan], b[:-1]])
    # 当日 a > b, 前日 a <= b
    return (a > b) & (prev_a <= prev_b)


# ===== 入口 API =====

def parse(src: str) -> Node:
    tokens = tokenize(src)
    parser = Parser(tokens)
    return parser.parse()


def evaluate_formula(formula: str, daily_df: pd.DataFrame, scalars: Dict[str, float] = None) -> Tuple[bool, Dict[str, Any]]:
    """对单只股票评估一条公式,返回 (是否命中, 上下文信息)。

    daily_df: 至少含 date/open/high/low/close/volume 等,按日期升序。
    scalars: 标量字段 (rps50/rps120/... 等)。
    """
    scalars = scalars or {}
    ast = parse(formula)
    series = _build_series(daily_df)
    ctx: Dict[str, Any] = {'series': series, 'scalars': scalars, 'locals': {}}
    try:
        result = Evaluator(ast).eval(ctx)
    except FormulaError as e:
        raise FormulaError(f'求值失败: {e}') from e

    # 兜底: 如果最后结果是序列,取最后一日
    if isinstance(result, np.ndarray):
        if result.size == 0:
            return False, {}
        # 用最后一日的值判断
        last = result[-1]
        if isinstance(last, np.bool_):
            return bool(last), {'last_value': bool(last)}
        try:
            return bool(last) and not np.isnan(last), {'last_value': float(last)}
        except (TypeError, ValueError):
            return bool(last), {'last_value': last}
    if isinstance(result, (bool, np.bool_)):
        return bool(result), {}
    return _truthy(result), {'last_value': result}


def _build_series(daily_df: pd.DataFrame) -> Dict[str, np.ndarray]:
    if daily_df is None or daily_df.empty:
        return {}
    close = pd.Series(daily_df['close'].astype(float).values)
    high = pd.Series(daily_df['high'].astype(float).values)
    low = pd.Series(daily_df['low'].astype(float).values)
    volume = pd.Series(daily_df['volume'].astype(float).values)

    n = len(close)
    # 9 日窗口:高=max(high, close) 联合,低=min(low, close) 联合,避免 RSV 越界
    eff_high = pd.concat([high, close], axis=1).max(axis=1)
    eff_low = pd.concat([low, close], axis=1).min(axis=1)
    hh_n = eff_high.rolling(9, min_periods=1).max()
    ll_n = eff_low.rolling(9, min_periods=1).min()
    denom = (hh_n - ll_n).replace(0, np.nan)
    rsv = (close - ll_n) / denom * 100
    rsv = rsv.where(~(denom.isna()), 50.0)
    rsv = rsv.values
    k_prev = 50.0
    d_prev = 50.0
    K = np.empty(n)
    D = np.empty(n)
    for i in range(n):
        v = rsv[i]
        if np.isnan(v):
            K[i], D[i] = np.nan, np.nan
            continue
        k_prev = (2 / 3) * k_prev + (1 / 3) * v
        d_prev = (2 / 3) * d_prev + (1 / 3) * k_prev
        K[i], D[i] = k_prev, d_prev
    J = 3 * K - 2 * D

    return {
        'close': close.values, 'open': daily_df['open'].astype(float).values,
        'high': high.values, 'low': low.values, 'volume': volume.values,
        'ma5': close.rolling(5, min_periods=1).mean().values,
        'ma10': close.rolling(10, min_periods=1).mean().values,
        'ma20': close.rolling(20, min_periods=1).mean().values,
        'ma60': close.rolling(60, min_periods=1).mean().values,
        'ma120': close.rolling(120, min_periods=1).mean().values,
        'ma250': close.rolling(250, min_periods=1).mean().values,
        'ema10': close.ewm(span=10, adjust=False).mean().values,
        'ema12': close.ewm(span=12, adjust=False).mean().values,
        'ema26': close.ewm(span=26, adjust=False).mean().values,
        'kdj_k': K, 'kdj_d': D, 'kdj_j': J,
    }


def validate(formula: str) -> Dict[str, Any]:
    """校验公式可解析 + 引用字段都认识。返回 valid/errors/normalized_formula/used_fields。"""
    try:
        ast = parse(formula)
    except FormulaError as e:
        return {'valid': False, 'errors': [str(e)], 'used_fields': [], 'normalized_formula': formula}

    used: List[str] = []
    for node in _walk(ast):
        if isinstance(node, FieldRef):
            key = FIELD_ALIASES.get(node.name.upper(), node.name.lower())
            if key not in used:
                used.append(key)
        if isinstance(node, FuncCall):
            for sub in node.args:
                if isinstance(sub, FieldRef):
                    key = FIELD_ALIASES.get(sub.name.upper(), sub.name.lower())
                    if key not in used:
                        used.append(key)
    return {
        'valid': True,
        'errors': [],
        'used_fields': sorted(used),
        'normalized_formula': formula,
    }


def _walk(node: Node):
    yield node
    for attr in ('left', 'right', 'operand', 'value', 'args', 'stmts', 'final'):
        v = getattr(node, attr, None)
        if v is None:
            continue
        if isinstance(v, list):
            for item in v:
                yield from _walk(item)
        elif isinstance(v, Node):
            yield from _walk(v)
