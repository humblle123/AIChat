"""SQLite 数据存储层"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
import pandas as pd
from config import DB_PATH, DATA_DIR
import os
import json

os.makedirs(DATA_DIR, exist_ok=True)


DEFAULT_FORMULA_TEMPLATES = [
    {
        "strategy_id": "b1",
        "name": "空谷幽兰",
        "group_name": "技术面",
        "description": "KDJ超卖 + 多空线突破",
        "expression": "KDJ_J < 18 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX",
        "params_schema": {
            "j_threshold": 18,
            "zx_emaperiod": 10,
        },
        "tags": ["KDJ", "突破", "技术面"],
        "source": "ai-project/stock-board",
    },
    {
        "strategy_id": "s2",
        "name": "月线反转",
        "group_name": "月线反转",
        "description": "站上年线 + 50日新高 + RPS强度",
        "expression": (
            "CLOSE > MA(CLOSE, 250) AND COUNT(HIGH >= HHV(HIGH, 50), 30) > 0 "
            "AND RPS50 >= 85 AND COUNT(CLOSE > MA(CLOSE, 250), 30) > 2 "
            "AND COUNT(CLOSE > MA(CLOSE, 250), 30) < 30 AND CLOSE / HHV(HIGH, 100) > 0.9"
        ),
        "params_schema": {
            "ma_period": 250,
            "new_high_days": 50,
            "min_rps50": 85,
            "min_above_ma_days": 2,
            "max_above_ma_days": 30,
        },
        "tags": ["欧奈尔", "趋势", "突破"],
        "source": "ai-project/stock-board",
    },
    {
        "strategy_id": "s3",
        "name": "RPS三线红",
        "group_name": "RPS红系",
        "description": "RPS50/120/250 同时强势且接近250日高点",
        "expression": "RPS50 > 90 AND RPS120 > 93 AND RPS250 > 95 AND CLOSE / HHV(HIGH, 250) > 0.85",
        "params_schema": {
            "min_rps50": 90,
            "min_rps120": 93,
            "min_rps250": 95,
            "near_high_threshold": 0.85,
        },
        "tags": ["RPS", "强势", "三线红"],
        "source": "ai-project/stock-board",
    },
    {
        "strategy_id": "kd1",
        "name": "一线红",
        "group_name": "RPS红系",
        "description": "任一RPS极强且距离250日高点较近",
        "expression": "(RPS50 > 95 OR RPS120 > 95 OR RPS250 > 95) AND CLOSE / HHV(HIGH, 250) > 0.6",
        "params_schema": {
            "min_rps": 95,
            "near_high_threshold": 0.6,
        },
        "tags": ["RPS", "强势", "一线红"],
        "source": "ai-project/stock-board",
    },
]


def _safe_json_loads(value: Any, default: Any):
    """安全解析 JSON 字符串。"""
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _normalize_concept_tags(stock: Dict) -> List[str]:
    """将概念字段统一成字符串列表。"""
    raw = stock.get('concept_tags', stock.get('concept'))
    if raw is None or raw == '':
        return []
    # pandas/numpy 数组/Series: 用 size 判断
    try:
        if hasattr(raw, 'size') and raw.size == 0:
            return []
    except Exception:
        pass
    try:
        if pd.isna(raw):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        parsed = _safe_json_loads(text, None)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        for sep in ['|', ',', '，', ';', '、', '/']:
            if sep in text:
                parts = [part.strip() for part in text.split(sep)]
                parts = [part for part in parts if part]
                if parts:
                    return parts
        return [text]
    return [str(raw).strip()]


def _coerce_flag(value: Any) -> int:
    """将布尔/数值/空值统一转成 0/1。"""
    if value in (None, '') or pd.isna(value):
        return 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in {'1', 'true', 'yes', 'y'} else 0
    return 1 if bool(value) else 0


def _normalize_stock_code(code: Any) -> Optional[str]:
    """统一股票代码格式为 6 位纯数字代码。"""
    if code in (None, '') or pd.isna(code):
        return None
    text = str(code).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith(('sh', 'sz', 'bj')) and len(text) >= 8:
        text = text[2:]
    return text


def _normalize_code_list(codes: List[Any]) -> List[str]:
    normalized = []
    seen = set()
    for code in codes:
        value = _normalize_stock_code(code)
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _stock_basic_payload(stock: Dict) -> Dict[str, Any]:
    """规范化 stock_basic 写入数据。"""
    concept_tags = _normalize_concept_tags(stock)
    listed_date = stock.get('listed_date') or stock.get('list_date')
    if pd.isna(listed_date):
        listed_date = None
    return {
        'code': _normalize_stock_code(stock.get('code')),
        'name': stock.get('name'),
        'market': stock.get('market'),
        'industry': stock.get('industry'),
        'concept_tags': json.dumps(concept_tags, ensure_ascii=False),
        'security_type': stock.get('security_type') or 'stock',
        'listed_date': listed_date,
        'is_delisted': _coerce_flag(stock.get('is_delisted', 0)),
        'is_st': _coerce_flag(stock.get('is_st', 0)),
        'is_suspended': _coerce_flag(stock.get('is_suspended', 0)),
    }


_CONN: Optional[sqlite3.Connection] = None
_CONN_LOCK = threading.Lock()


def get_conn() -> sqlite3.Connection:
    """获取数据库连接(单例长连接 + WAL)。"""
    global _CONN
    if _CONN is not None:
        return _CONN
    with _CONN_LOCK:
        if _CONN is None:
            conn = sqlite3.connect(
                DB_PATH,
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None,  # autocommit, 显式 commit
            )
            conn.row_factory = sqlite3.Row
            # WAL 模式 + 适度 cache,适合读多写少
            # (在某些只读/虚拟挂载文件系统上 PRAGMA 可能 I/O 失败,降级到默认)
            for pragma in [
                'PRAGMA journal_mode=WAL',
                'PRAGMA synchronous=NORMAL',
                'PRAGMA temp_store=MEMORY',
                'PRAGMA cache_size=-20000',
            ]:
                try:
                    conn.execute(pragma)
                except sqlite3.OperationalError:
                    pass
            _CONN = conn
        return _CONN


# ====== schema 迁移(集中式,避免 alembic 依赖) ======

SCHEMA_MIGRATIONS: Dict[str, Dict[str, str]] = {
    'template_screen_cache': {
        'market': 'TEXT',
        'industry': 'TEXT',
        'concept_tags': 'TEXT',
        'security_type': "TEXT DEFAULT 'stock'",
        'listed_date': 'TEXT',
        'listed_days': 'INTEGER DEFAULT 0',
        'price': 'REAL DEFAULT 0',
        'change': 'REAL DEFAULT 0',
        'change_pct': 'REAL DEFAULT 0',
        'volume': 'INTEGER DEFAULT 0',
        'amount': 'REAL DEFAULT 0',
        'total_mv': 'REAL DEFAULT 0',
        'circ_mv': 'REAL DEFAULT 0',
        'pe_ttm': 'REAL',
        'pb': 'REAL',
        'roe_ttm': 'REAL',
        'revenue_yoy_q': 'REAL',
        'net_profit_yoy_q': 'REAL',
        'rps50': 'REAL',
        'rps120': 'REAL',
        'rps250': 'REAL',
        'template_hits_json': 'TEXT',
    },
}


def _apply_pending_migrations(cursor) -> None:
    """对 SCHEMA_MIGRATIONS 中声明的列做幂等 ALTER。"""
    for table, columns in SCHEMA_MIGRATIONS.items():
        existing = {
            row['name'] for row in cursor.execute(f'PRAGMA table_info({table})').fetchall()
        }
        for col, col_type in columns.items():
            if col not in existing:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')


@contextmanager
def get_cursor():
    """上下文管理器: 复用单例连接,每次提交后立即 COMMIT。"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def init_db():
    """初始化数据库表结构"""
    with get_cursor() as cursor:
        # 股票基础信息表（标准基础表,作为唯一来源）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_basic (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market TEXT DEFAULT '',
                industry TEXT DEFAULT '',
                concept_tags TEXT,
                security_type TEXT DEFAULT 'stock',
                listed_date TEXT,
                is_delisted INTEGER DEFAULT 0,
                is_st INTEGER DEFAULT 0,
                is_suspended INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_basic_market ON stock_basic(market)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_basic_industry ON stock_basic(industry)")
        
        # 内置策略模板表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS formula_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                group_name TEXT,
                description TEXT,
                expression TEXT NOT NULL,
                params_schema TEXT,
                tags TEXT,
                enabled INTEGER DEFAULT 1,
                source TEXT DEFAULT 'builtin',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_formula_template_group ON formula_template(group_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_formula_template_enabled ON formula_template(enabled)")
        
        # 日线行情表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                pre_close REAL,
                volume INTEGER,
                amount REAL,
                up REAL,
                UNIQUE(code, date)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_code_date ON stock_daily(code, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON stock_daily(date)")

        # 行情快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_quote_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                price REAL,
                prev_close REAL,
                change REAL,
                change_pct REAL,
                volume INTEGER,
                amount REAL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                pe REAL,
                pb REAL,
                total_mv REAL,
                circ_mv REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, trade_date)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_quote_code_date ON stock_quote_snapshot(code, trade_date)")
        
        # RPS 预计算表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_rps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                rps5 REAL,
                rps10 REAL,
                rps15 REAL,
                rps20 REAL,
                rps50 REAL,
                rps120 REAL,
                rps250 REAL,
                UNIQUE(code, date)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rps_code_date ON stock_rps(code, date)")

        # K 线缓存表: 盘后预计算 日/周/月 K 线 + MA 系列,详情页直接读,不再实时算
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_kline_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                period TEXT NOT NULL DEFAULT 'day',
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                pre_close REAL,
                volume INTEGER,
                amount REAL,
                up REAL,
                ma5 REAL,
                ma20 REAL,
                ma60 REAL,
                ma120 REAL,
                ma250 REAL,
                kdj_k REAL,
                kdj_d REAL,
                kdj_j REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, period, date)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_cache_code_period ON stock_kline_cache(code, period, date)")

        # 选股公式表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS formulas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                code TEXT,
                params TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 选股结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screen_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                formula_id INTEGER,
                code TEXT NOT NULL,
                name TEXT,
                reason TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (formula_id) REFERENCES formulas(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_result_date_formula ON screen_results(date, formula_id)")

        # 内置模板预计算结果缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS template_screen_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                template_id INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                market TEXT,
                industry TEXT,
                concept_tags TEXT,
                security_type TEXT DEFAULT 'stock',
                listed_date TEXT,
                listed_days INTEGER DEFAULT 0,
                price REAL DEFAULT 0,
                change REAL DEFAULT 0,
                change_pct REAL DEFAULT 0,
                volume INTEGER DEFAULT 0,
                amount REAL DEFAULT 0,
                total_mv REAL DEFAULT 0,
                circ_mv REAL DEFAULT 0,
                pe_ttm REAL,
                pb REAL,
                roe_ttm REAL,
                revenue_yoy_q REAL,
                net_profit_yoy_q REAL,
                rps50 REAL,
                rps120 REAL,
                rps250 REAL,
                reason TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, template_id, code),
                FOREIGN KEY (template_id) REFERENCES formula_template(id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_cache_template_date "
            "ON template_screen_cache(template_id, date)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_cache_strategy_date "
            "ON template_screen_cache(strategy_id, date)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_cache_template_date_change "
            "ON template_screen_cache(template_id, date, change_pct)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_cache_template_date_price "
            "ON template_screen_cache(template_id, date, price)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_template_cache_template_date_rps50 "
            "ON template_screen_cache(template_id, date, rps50)"
        )

        # 集中式 schema 迁移(替代 alembic,适合 1-2 个表的轻量场景)
        # 新增字段时,在这里加一行即可,启动时幂等执行
        _apply_pending_migrations(cursor)
        
        # 插入默认公式（如果不存在）
        default_formulas = [
            ('B1-强势突破', '突破20日新高的强势股 RPS50>85', 
             'RPS50 := RANK(PCT_CHG(CLOSE, 50));\nFILTER := RPS50 > 85;',
             '{"min_rps50": 85}'),
            ('S2-月线反转', '月线反转信号选股 70<RPS50<90',
             'MA5 := MA(CLOSE, 5);\nMA20 := MA(CLOSE, 20);\nFILTER := MA5 > MA20 AND CLOSE > MA20;',
             '{"days": 10}'),
            ('S3-RPS三线红', 'RPS三线同时翻红 RPS50>90 AND RPS120>90',
             'RPS50 := RANK(PCT_CHG(CLOSE, 50));\nRPS120 := RANK(PCT_CHG(CLOSE, 120));\nFILTER := RPS50 > 90 AND RPS120 > 90;',
             '{"min_rps": 90}'),
            ('KD1战法', 'KDJ低位金叉',
             'RSV := (CLOSE - LLV(LOW, 9)) / (HHV(HIGH, 9) - LLV(LOW, 9)) * 100;\nK := SMA(RSV, 3, 1);\nD := SMA(K, 3, 1);\nFILTER := K < 30 AND CROSS(K, D);',
             '{"k_limit": 30, "d_limit": 30}'),
        ]
        
        cursor.execute("SELECT COUNT(*) FROM formulas")
        if cursor.fetchone()[0] == 0:
            for name, desc, code, params in default_formulas:
                cursor.execute("""
                    INSERT INTO formulas (name, description, code, params)
                    VALUES (?, ?, ?, ?)
                """, (name, desc, code, params))

        # 一次性把旧 stocks 表的数据并入 stock_basic (向后兼容)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'")
        has_legacy_stocks = cursor.fetchone() is not None
        if has_legacy_stocks:
            cursor.execute("SELECT COUNT(*) FROM stock_basic")
            stock_basic_count = cursor.fetchone()[0]
            if stock_basic_count == 0:
                cursor.execute("SELECT code, name, market, industry, concept, list_date FROM stocks")
                legacy_rows = cursor.fetchall()
                for row in legacy_rows:
                    concept_tags = _normalize_concept_tags({'concept': row['concept']})
                    cursor.execute("""
                        INSERT INTO stock_basic
                        (code, name, market, industry, concept_tags, security_type, listed_date, is_delisted, is_st, is_suspended)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(code) DO NOTHING
                    """, (
                        row['code'],
                        row['name'],
                        row['market'],
                        row['industry'],
                        json.dumps(concept_tags, ensure_ascii=False),
                        'stock',
                        row['list_date'],
                        0,
                        1 if ('ST' in (row['name'] or '') or '*ST' in (row['name'] or '')) else 0,
                        0,
                    ))
            # 迁移完成,删旧表
            cursor.execute("DROP TABLE IF EXISTS stocks")

        # 预置内置模板
        cursor.execute("SELECT COUNT(*) FROM formula_template")
        if cursor.fetchone()[0] == 0:
            for template in DEFAULT_FORMULA_TEMPLATES:
                cursor.execute("""
                    INSERT INTO formula_template
                    (strategy_id, name, group_name, description, expression, params_schema, tags, enabled, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    template['strategy_id'],
                    template['name'],
                    template['group_name'],
                    template['description'],
                    template['expression'],
                    json.dumps(template['params_schema'], ensure_ascii=False),
                    json.dumps(template['tags'], ensure_ascii=False),
                    1,
                    template['source'],
                ))
        
        print("[DB] 数据库初始化完成")


def save_stock_basic(stocks: List[Dict]):
    """保存股票基础信息到 stock_basic。"""
    with get_cursor() as cursor:
        for stock in stocks:
            payload = _stock_basic_payload(stock)
            market = payload['market'] or ''
            industry = payload['industry'] or ''
            cursor.execute("""
                INSERT INTO stock_basic
                (code, name, market, industry, concept_tags, security_type, listed_date, is_delisted, is_st, is_suspended)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    market = excluded.market,
                    industry = excluded.industry,
                    concept_tags = excluded.concept_tags,
                    security_type = excluded.security_type,
                    listed_date = excluded.listed_date,
                    is_delisted = excluded.is_delisted,
                    is_st = excluded.is_st,
                    is_suspended = excluded.is_suspended,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                payload['code'],
                payload['name'],
                market,
                industry,
                payload['concept_tags'],
                payload['security_type'],
                payload['listed_date'],
                payload['is_delisted'],
                payload['is_st'],
                payload['is_suspended'],
            ))


def save_daily_data(code: str, data: List[Dict]):
    """保存日线数据"""
    normalized_code = _normalize_stock_code(code)
    if not normalized_code:
        return
    with get_cursor() as cursor:
        for day in data:
            trade_date = day.get('date')
            if hasattr(trade_date, 'strftime'):
                trade_date = trade_date.strftime('%Y-%m-%d')
            elif trade_date is not None:
                trade_date = str(trade_date)
            cursor.execute("""
                INSERT INTO stock_daily
                (code, date, open, high, low, close, pre_close, volume, amount, up)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    pre_close = excluded.pre_close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    up = excluded.up
            """, (
                normalized_code,
                trade_date,
                day.get('open'),
                day.get('high'),
                day.get('low'),
                day.get('close'),
                day.get('pre_close'),
                day.get('volume'),
                day.get('amount'),
                day.get('up'),
            ))


def save_quote_snapshots(quotes: List[Dict], trade_date: str):
    """保存行情快照。"""
    if not quotes:
        return
    with get_cursor() as cursor:
        for quote in quotes:
            normalized_code = _normalize_stock_code(quote.get('code'))
            if not normalized_code:
                continue
            price = quote.get('price')
            prev_close = quote.get('close')
            change = None
            if price is not None and prev_close is not None:
                change = float(price) - float(prev_close)
            cursor.execute("""
                INSERT INTO stock_quote_snapshot
                (code, trade_date, price, prev_close, change, change_pct, volume, amount, open, high, low, close, pe, pb, total_mv, circ_mv)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, trade_date) DO UPDATE SET
                    price = excluded.price,
                    prev_close = excluded.prev_close,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    pe = excluded.pe,
                    pb = excluded.pb,
                    total_mv = excluded.total_mv,
                    circ_mv = excluded.circ_mv
            """, (
                normalized_code,
                trade_date,
                quote.get('price'),
                quote.get('close'),
                change,
                quote.get('up'),
                quote.get('volume'),
                quote.get('amount'),
                quote.get('open'),
                quote.get('high'),
                quote.get('low'),
                quote.get('close'),
                quote.get('pe'),
                quote.get('pb'),
                quote.get('total_mv'),
                quote.get('circ_mv'),
            ))


def repair_daily_pre_close(max_ratio: float = 3.0) -> int:
    """修复明显异常的昨收值，回填为上一交易日收盘价。"""
    with get_cursor() as cursor:
        cursor.execute("""
            WITH previous_close AS (
                SELECT
                    current.id AS current_id,
                    previous.close AS expected_pre_close
                FROM stock_daily current
                JOIN stock_daily previous
                  ON previous.code = current.code
                 AND previous.date = (
                     SELECT MAX(prev2.date)
                     FROM stock_daily prev2
                     WHERE prev2.code = current.code
                       AND prev2.date < current.date
                 )
                WHERE current.pre_close IS NULL
                   OR current.pre_close <= 0
                   OR current.close IS NULL
                   OR current.close <= 0
                   OR current.pre_close > current.close * ?
                   OR current.pre_close < current.close / ?
            )
            UPDATE stock_daily
            SET pre_close = (
                SELECT expected_pre_close
                FROM previous_close
                WHERE previous_close.current_id = stock_daily.id
            )
            WHERE id IN (SELECT current_id FROM previous_close)
        """, (max_ratio, max_ratio))
        repaired = cursor.rowcount if cursor.rowcount is not None else 0
    return repaired


def get_latest_quote_snapshot(codes: List[str] = None) -> pd.DataFrame:
    """获取最新行情快照。"""
    if codes:
        codes = _normalize_code_list(codes)
        if not codes:
            return pd.DataFrame()
        placeholders = ','.join('?' * len(codes))
        code_clause = f"WHERE sqq.code IN ({placeholders})"
        params = codes
    else:
        code_clause = ""
        params = []

    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT sqq.*
            FROM stock_quote_snapshot sqq
            INNER JOIN (
                SELECT code, MAX(trade_date) AS max_trade_date
                FROM stock_quote_snapshot
                GROUP BY code
            ) latest
            ON sqq.code = latest.code AND sqq.trade_date = latest.max_trade_date
            {code_clause}
            ORDER BY sqq.code
        """, params)
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(row) for row in rows])
    return df


def get_stocks() -> pd.DataFrame:
    """获取所有股票(仅 stock_basic)。"""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT code, name, market, industry, concept_tags, security_type, listed_date,
                   is_delisted, is_st, is_suspended
            FROM stock_basic
            ORDER BY code
        """)
        rows = cursor.fetchall()
    df = pd.DataFrame([dict(row) for row in rows])
    return df


def get_stocks_by_codes(codes: List[str]) -> pd.DataFrame:
    """按代码获取股票列表(仅 stock_basic)。"""
    codes = _normalize_code_list(codes)
    if not codes:
        return pd.DataFrame()

    placeholders = ','.join('?' * len(codes))
    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT code, name, market, industry, concept_tags, security_type, listed_date,
                   is_delisted, is_st, is_suspended
            FROM stock_basic
            WHERE code IN ({placeholders})
            ORDER BY code
        """, codes)
        rows = cursor.fetchall()

    df = pd.DataFrame([dict(row) for row in rows])
    return df


def get_stock_basic_by_code(code: str) -> Optional[Dict[str, Any]]:
    """按代码获取单只股票基础信息。"""
    code = _normalize_stock_code(code)
    if not code:
        return None
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT code, name, market, industry, concept_tags, security_type, listed_date,
                   is_delisted, is_st, is_suspended
            FROM stock_basic
            WHERE code = ?
        """, (code,))
        row = cursor.fetchone()
        if not row:
            return None
        stock = dict(row)
        stock['concept_tags'] = _safe_json_loads(stock.get('concept_tags'), [])
        if not isinstance(stock['concept_tags'], list):
            stock['concept_tags'] = _normalize_concept_tags(stock)
        return stock


def get_daily_data(codes: List[str], days: int = 600) -> Dict[str, pd.DataFrame]:
    """获取日线数据，按股票分组"""
    codes = _normalize_code_list(codes)
    if not codes:
        return {}
    
    placeholders = ','.join('?' * len(codes))
    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT code, date, open, high, low, close, pre_close, volume, amount, up
            FROM stock_daily
            WHERE code IN ({placeholders})
            ORDER BY code, date
        """, codes)
        rows = cursor.fetchall()
    
    if not rows:
        return {}
    
    df = pd.DataFrame([dict(row) for row in rows])
    if df.empty:
        return {}
    
    # 按日期过滤
    df['date'] = pd.to_datetime(df['date'])
    cutoff = df['date'].max() - pd.Timedelta(days=days)
    df = df[df['date'] >= cutoff]
    
    result = {}
    for code, group in df.groupby('code'):
        group = group.drop(columns=['code']).sort_values('date').reset_index(drop=True)
        result[code] = group
    
    return result


def get_daily_data_df(codes: List[str] = None, days: int = 600) -> pd.DataFrame:
    """获取日线数据，返回单个DataFrame"""
    # 先查最大交易日，用于在 SQL 层过滤日期，避免将全量数据加载到内存
    with get_cursor() as cursor:
        cursor.execute("SELECT MAX(date) FROM stock_daily")
        max_date_row = cursor.fetchone()
    if not max_date_row or not max_date_row[0]:
        return pd.DataFrame()

    max_date_str = str(max_date_row[0])
    cutoff_dt = pd.to_datetime(max_date_str) - pd.Timedelta(days=days)
    cutoff_str = cutoff_dt.strftime('%Y-%m-%d')

    conditions = ["date >= ?"]
    params: list = [cutoff_str]

    if codes:
        codes = _normalize_code_list(codes)
        if not codes:
            return pd.DataFrame()
        placeholders = ','.join('?' * len(codes))
        conditions.append(f"code IN ({placeholders})")
        params.extend(codes)

    where_clause = "WHERE " + " AND ".join(conditions)

    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT code, date, open, high, low, close, pre_close, volume, amount, up
            FROM stock_daily
            {where_clause}
            ORDER BY code, date
        """, params)
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(row) for row in rows])
    df['date'] = pd.to_datetime(df['date'])

    return df


def get_rps_data(codes: List[str] = None) -> Optional[pd.DataFrame]:
    """获取预计算的 RPS 数据"""
    conditions = []
    params = []
    if codes:
        codes = _normalize_code_list(codes)
        if not codes:
            return None
        placeholders = ','.join('?' * len(codes))
        conditions.append(f"sr.code IN ({placeholders})")
        params.extend(codes)
    
    with get_cursor() as cursor:
        # 获取每个股票最新日期的RPS
        conditions.append("sr.date = (SELECT MAX(date) FROM stock_rps WHERE code = sr.code)")
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        cursor.execute(f"""
            SELECT sr.code, sr.date, sr.rps5, sr.rps10, sr.rps15, sr.rps20, sr.rps50, sr.rps120, sr.rps250,
                   sb.name AS name
            FROM stock_rps sr
            LEFT JOIN stock_basic sb ON sr.code = sb.code
            {where_clause}
        """, params)
        rows = cursor.fetchall()
    
    if not rows:
        return None

    df = pd.DataFrame([dict(row) for row in rows])
    if not df.empty and 'code' in df.columns:
        df = df.set_index('code', drop=False)
    return df


def get_rps_history(code: str, days: int = 250) -> Optional[pd.DataFrame]:
    """获取单只股票的 RPS 历史序列。"""
    normalized_code = _normalize_stock_code(code)
    if not normalized_code:
        return None

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT code, date, rps5, rps10, rps15, rps20, rps50, rps120, rps250
            FROM stock_rps
            WHERE code = ?
            ORDER BY date DESC
            """,
            (normalized_code,),
        )
        rows = cursor.fetchall()

    if not rows:
        return None

    df = pd.DataFrame([dict(row) for row in rows])
    if df.empty:
        return None
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df[df['date'].notna()].copy()
    if df.empty:
        return None
    df = df.sort_values('date').reset_index(drop=True)
    if days and days > 0:
        df = df.tail(days).copy()
    return df


def get_latest_date() -> str:
    """获取最新交易日"""
    with get_cursor() as cursor:
        cursor.execute("SELECT MAX(date) FROM stock_daily")
        row = cursor.fetchone()
        return row[0] if row else None


def get_latest_daily_date_by_code(code: str) -> Optional[str]:
    """获取单只股票最新日线日期。"""
    normalized_code = _normalize_stock_code(code)
    if not normalized_code:
        return None
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT MAX(date) FROM stock_daily WHERE code = ?",
            (normalized_code,),
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else None


def get_latest_daily_codes() -> pd.DataFrame:
    """获取每只股票最新一条日线所属的日期。"""
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT code, MAX(date) AS latest_date
            FROM stock_daily
            GROUP BY code
            """
        )
        rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame(columns=['code', 'latest_date'])
    df = pd.DataFrame([dict(row) for row in rows])
    df['latest_date'] = pd.to_datetime(df['latest_date'], errors='coerce')
    return df


def get_codes_needing_daily_update(reference_date: str = None, codes: List[str] = None) -> List[str]:
    """找出尚未更新到 reference_date 的股票代码。"""
    codes = _normalize_code_list(codes) if codes else None
    with get_cursor() as cursor:
        if codes:
            placeholders = ','.join('?' * len(codes))
            cursor.execute(
                f"""
                SELECT code, MAX(date) AS latest_date
                FROM stock_daily
                WHERE code IN ({placeholders})
                GROUP BY code
                """,
                codes,
            )
        else:
            cursor.execute(
                f"""
                SELECT code, MAX(date) AS latest_date
                FROM stock_daily
                GROUP BY code
                """,
            )
        rows = cursor.fetchall()

    if not rows:
        return codes or []

    if not reference_date:
        return [str(row['code']) for row in rows]

    target = pd.to_datetime(reference_date, errors='coerce')
    if pd.isna(target):
        return [str(row['code']) for row in rows]

    result = []
    for row in rows:
        latest_date = pd.to_datetime(row['latest_date'], errors='coerce')
        if pd.isna(latest_date) or latest_date < target:
            result.append(str(row['code']))
    return result


def normalize_stock_code_tables() -> Dict[str, int]:
    """一次性归一化数据库中的股票代码格式。"""
    stats: Dict[str, int] = {}
    with get_cursor() as cursor:
        prefix_predicate = "lower(code) LIKE 'sh%' OR lower(code) LIKE 'sz%' OR lower(code) LIKE 'bj%'"

        cursor.execute(f"""
            DELETE FROM stock_basic
            WHERE rowid IN (
                WITH ranked AS (
                    SELECT
                        rowid,
                        ROW_NUMBER() OVER (
                            PARTITION BY CASE WHEN {prefix_predicate} THEN substr(code, 3) ELSE code END
                            ORDER BY
                                CASE WHEN code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' THEN 0 ELSE 1 END,
                                updated_at DESC,
                                created_at DESC
                        ) AS rn
                    FROM stock_basic
                )
                SELECT rowid FROM ranked WHERE rn > 1
            )
        """)
        cursor.execute(f"UPDATE stock_basic SET code = substr(code, 3) WHERE {prefix_predicate}")
        cursor.execute("SELECT COUNT(*) FROM stock_basic")
        stats['stock_basic'] = cursor.fetchone()[0]

        cursor.execute(f"""
            DELETE FROM stock_daily
            WHERE id IN (
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY CASE WHEN {prefix_predicate} THEN substr(code, 3) ELSE code END, date
                            ORDER BY
                                CASE WHEN code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' THEN 0 ELSE 1 END,
                                id DESC
                        ) AS rn
                    FROM stock_daily
                )
                SELECT id FROM ranked WHERE rn > 1
            )
        """)
        cursor.execute(f"UPDATE stock_daily SET code = substr(code, 3) WHERE {prefix_predicate}")
        cursor.execute("SELECT COUNT(*) FROM stock_daily")
        stats['stock_daily'] = cursor.fetchone()[0]

        cursor.execute(f"""
            DELETE FROM stock_rps
            WHERE id IN (
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY CASE WHEN {prefix_predicate} THEN substr(code, 3) ELSE code END, date
                            ORDER BY
                                CASE WHEN code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' THEN 0 ELSE 1 END,
                                id DESC
                        ) AS rn
                    FROM stock_rps
                )
                SELECT id FROM ranked WHERE rn > 1
            )
        """)
        cursor.execute(f"UPDATE stock_rps SET code = substr(code, 3) WHERE {prefix_predicate}")
        cursor.execute("SELECT COUNT(*) FROM stock_rps")
        stats['stock_rps'] = cursor.fetchone()[0]

        cursor.execute(f"""
            DELETE FROM stock_quote_snapshot
            WHERE id IN (
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY CASE WHEN {prefix_predicate} THEN substr(code, 3) ELSE code END, trade_date
                            ORDER BY
                                CASE WHEN code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' THEN 0 ELSE 1 END,
                                id DESC
                        ) AS rn
                    FROM stock_quote_snapshot
                )
                SELECT id FROM ranked WHERE rn > 1
            )
        """)
        cursor.execute(f"UPDATE stock_quote_snapshot SET code = substr(code, 3) WHERE {prefix_predicate}")
        cursor.execute("SELECT COUNT(*) FROM stock_quote_snapshot")
        stats['stock_quote_snapshot'] = cursor.fetchone()[0]

        cursor.execute(f"""
            DELETE FROM template_screen_cache
            WHERE id IN (
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY CASE WHEN {prefix_predicate} THEN substr(code, 3) ELSE code END, date, template_id
                            ORDER BY
                                CASE WHEN code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' THEN 0 ELSE 1 END,
                                id DESC
                        ) AS rn
                    FROM template_screen_cache
                )
                SELECT id FROM ranked WHERE rn > 1
            )
        """)
        cursor.execute(f"UPDATE template_screen_cache SET code = substr(code, 3) WHERE {prefix_predicate}")
        cursor.execute("SELECT COUNT(*) FROM template_screen_cache")
        stats['template_screen_cache'] = cursor.fetchone()[0]
    return stats


def save_rps_data(code: str, date: str, rps_values: Dict[str, float]):
    """保存 RPS 数据"""
    normalized_code = _normalize_stock_code(code)
    if not normalized_code:
        return
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO stock_rps
            (code, date, rps5, rps10, rps15, rps20, rps50, rps120, rps250)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, date) DO UPDATE SET
                rps5 = excluded.rps5,
                rps10 = excluded.rps10,
                rps15 = excluded.rps15,
                rps20 = excluded.rps20,
                rps50 = excluded.rps50,
                rps120 = excluded.rps120,
                rps250 = excluded.rps250
        """, (
            normalized_code, date,
            rps_values.get('rps5'),
            rps_values.get('rps10'),
            rps_values.get('rps15'),
            rps_values.get('rps20'),
            rps_values.get('rps50'),
            rps_values.get('rps120'),
            rps_values.get('rps250'),
        ))


# ====== 公式管理 CRUD ======

def get_formulas() -> List[Dict]:
    """获取所有公式"""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, name, description, code, params, is_active, created_at, updated_at
            FROM formulas
            ORDER BY id
        """)
        rows = cursor.fetchall()
        formulas = []
        for row in rows:
            f = dict(row)
            f['params'] = json.loads(f['params']) if f['params'] else {}
            formulas.append(f)
        return formulas


def get_formula_templates() -> List[Dict]:
    """获取所有内置策略模板。"""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, strategy_id, name, group_name, description, expression,
                   params_schema, tags, enabled, source, created_at, updated_at
            FROM formula_template
            ORDER BY id
        """)
        rows = cursor.fetchall()
        templates = []
        for row in rows:
            t = dict(row)
            t['params_schema'] = _safe_json_loads(t['params_schema'], {})
            t['tags'] = _safe_json_loads(t['tags'], [])
            templates.append(t)
        return templates


def get_formula_template_by_id(template_id: int) -> Optional[Dict]:
    """根据ID获取内置策略模板。"""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, strategy_id, name, group_name, description, expression,
                   params_schema, tags, enabled, source, created_at, updated_at
            FROM formula_template
            WHERE id = ?
        """, (template_id,))
        row = cursor.fetchone()
        if row:
            t = dict(row)
            t['params_schema'] = _safe_json_loads(t['params_schema'], {})
            t['tags'] = _safe_json_loads(t['tags'], [])
            return t
        return None


def get_formula_by_id(formula_id: int) -> Optional[Dict]:
    """根据ID获取公式"""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, name, description, code, params, is_active, created_at, updated_at
            FROM formulas
            WHERE id = ?
        """, (formula_id,))
        row = cursor.fetchone()
        if row:
            f = dict(row)
            f['params'] = json.loads(f['params']) if f['params'] else {}
            return f
        return None


def create_formula(name: str, description: str = '', code: str = '', params: Dict = None) -> int:
    """创建新公式"""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO formulas (name, description, code, params)
            VALUES (?, ?, ?, ?)
        """, (name, description, code, json.dumps(params or {})))
        return cursor.lastrowid


def update_formula(formula_id: int, name: str = None, description: str = None, 
                   code: str = None, params: Dict = None) -> bool:
    """更新公式"""
    updates = []
    values = []
    
    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if code is not None:
        updates.append("code = ?")
        values.append(code)
    if params is not None:
        updates.append("params = ?")
        values.append(json.dumps(params))
    
    if not updates:
        return False
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(formula_id)
    
    with get_cursor() as cursor:
        cursor.execute(f"""
            UPDATE formulas SET {', '.join(updates)} WHERE id = ?
        """, values)
        return cursor.rowcount > 0


def delete_formula(formula_id: int) -> bool:
    """删除公式"""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM formulas WHERE id = ?", (formula_id,))
        return cursor.rowcount > 0


# ====== 选股结果管理 ======

def save_screen_result(date: str, formula_id: int, results: List[Dict]):
    """保存选股结果"""
    with get_cursor() as cursor:
        for result in results:
            cursor.execute("""
                INSERT INTO screen_results (date, formula_id, code, name, reason, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                date,
                formula_id,
                result.get('code'),
                result.get('name'),
                result.get('reason', ''),
                json.dumps(result.get('metadata', {})),
            ))


def save_template_screen_results(date: str, template_id: int, strategy_id: str, results: List[Dict]):
    """保存内置模板预计算结果。

    results 可以是只含 code/name 的策略命中结果，也可以是已经富化好的
    前端列表快照。富化字段会一起落库，让前端切换策略时只读小表。
    """
    with get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM template_screen_cache WHERE date = ? AND template_id = ?",
            (date, template_id),
        )
        for result in results:
            normalized_code = _normalize_stock_code(result.get('code'))
            if not normalized_code:
                continue
            cursor.execute("""
                INSERT INTO template_screen_cache
                (
                    date, template_id, strategy_id, code, name,
                    market, industry, concept_tags, security_type, listed_date, listed_days,
                    price, change, change_pct, volume, amount, total_mv, circ_mv,
                    pe_ttm, pb, roe_ttm, revenue_yoy_q, net_profit_yoy_q,
                    rps50, rps120, rps250, reason, metadata, template_hits_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, template_id, code) DO UPDATE SET
                    strategy_id = excluded.strategy_id,
                    name = excluded.name,
                    market = excluded.market,
                    industry = excluded.industry,
                    concept_tags = excluded.concept_tags,
                    security_type = excluded.security_type,
                    listed_date = excluded.listed_date,
                    listed_days = excluded.listed_days,
                    price = excluded.price,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    total_mv = excluded.total_mv,
                    circ_mv = excluded.circ_mv,
                    pe_ttm = excluded.pe_ttm,
                    pb = excluded.pb,
                    roe_ttm = excluded.roe_ttm,
                    revenue_yoy_q = excluded.revenue_yoy_q,
                    net_profit_yoy_q = excluded.net_profit_yoy_q,
                    rps50 = excluded.rps50,
                    rps120 = excluded.rps120,
                    rps250 = excluded.rps250,
                    reason = excluded.reason,
                    metadata = excluded.metadata,
                    template_hits_json = excluded.template_hits_json
            """, (
                date,
                template_id,
                strategy_id,
                normalized_code,
                result.get('name'),
                result.get('market', ''),
                result.get('industry', ''),
                json.dumps(_normalize_concept_tags({'concept_tags': result.get('concept_tags')}), ensure_ascii=False),
                result.get('security_type', 'stock'),
                result.get('listed_date', ''),
                int(result.get('listed_days') or 0),
                float(result.get('price') or 0),
                float(result.get('change') or 0),
                float(result.get('change_pct') or 0),
                int(result.get('volume') or 0),
                float(result.get('amount') or 0),
                float(result.get('total_mv') or 0),
                float(result.get('circ_mv') or 0),
                result.get('pe_ttm'),
                result.get('pb'),
                result.get('roe_ttm'),
                result.get('revenue_yoy_q'),
                result.get('net_profit_yoy_q'),
                result.get('rps50'),
                result.get('rps120'),
                result.get('rps250'),
                result.get('reason', ''),
                json.dumps(result.get('metadata', {}), ensure_ascii=False),
                result.get('template_hits_json'),
            ))


def get_template_screen_results(template_id: int, date: str = None) -> Dict[str, Any]:
    """获取内置模板预计算结果。"""
    with get_cursor() as cursor:
        target_date = date
        if not target_date:
            cursor.execute(
                "SELECT MAX(date) FROM template_screen_cache WHERE template_id = ?",
                (template_id,),
            )
            row = cursor.fetchone()
            target_date = row[0] if row else None

        if not target_date:
            return {'date': '', 'items': []}

        cursor.execute("""
            SELECT id, date, template_id, strategy_id, code, name,
                   market, industry, concept_tags, security_type, listed_date, listed_days,
                   price, change, change_pct, volume, amount, total_mv, circ_mv,
                   pe_ttm, pb, roe_ttm, revenue_yoy_q, net_profit_yoy_q,
                   rps50, rps120, rps250, reason, metadata
            FROM template_screen_cache
            WHERE template_id = ? AND date = ?
            ORDER BY id
        """, (template_id, target_date))
        rows = cursor.fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item['metadata'] = _safe_json_loads(item.get('metadata'), {})
        item['concept_tags'] = _safe_json_loads(item.get('concept_tags'), [])
        if not isinstance(item['concept_tags'], list):
            item['concept_tags'] = _normalize_concept_tags({'concept_tags': item.get('concept_tags')})
        results.append(item)
    return {'date': target_date, 'items': results}


def get_template_screen_summary(date: str = None) -> List[Dict[str, Any]]:
    """获取内置模板最新缓存摘要，供左侧数量展示使用。"""
    with get_cursor() as cursor:
        if date:
            cursor.execute("""
                SELECT tsc.template_id, tsc.strategy_id, ft.name, ft.description, ft.expression,
                       tsc.date, COUNT(*) AS total
                FROM template_screen_cache tsc
                LEFT JOIN formula_template ft ON ft.id = tsc.template_id
                WHERE tsc.date = ?
                GROUP BY tsc.template_id, tsc.strategy_id, tsc.date
                ORDER BY tsc.template_id
            """, (date,))
        else:
            cursor.execute("""
                SELECT tsc.template_id, tsc.strategy_id, ft.name, ft.description, ft.expression,
                       tsc.date, COUNT(*) AS total
                FROM template_screen_cache tsc
                LEFT JOIN formula_template ft ON ft.id = tsc.template_id
                INNER JOIN (
                    SELECT template_id, MAX(date) AS max_date
                    FROM template_screen_cache
                    GROUP BY template_id
                ) latest
                ON latest.template_id = tsc.template_id AND latest.max_date = tsc.date
                GROUP BY tsc.template_id, tsc.strategy_id, tsc.date
                ORDER BY tsc.template_id
            """)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_template_hits_for_code(code: str) -> List[Dict[str, Any]]:
    """从 template_screen_cache 读单只股票的 template_hits_json(盘后预计算结果)。

    返回 list[dict],每项是 {template_id, strategy_id, name, group_name, reason, matched}。
    """
    normalized = _normalize_stock_code(code)
    if not normalized:
        return []
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT template_hits_json
            FROM template_screen_cache
            WHERE code = ?
              AND date = (SELECT MAX(date) FROM template_screen_cache WHERE code = ?)
            LIMIT 1
        """, (normalized, normalized))
        row = cursor.fetchone()
    if not row or not row['template_hits_json']:
        return []
    try:
        data = json.loads(row['template_hits_json'])
        if isinstance(data, list):
            return data
    except (TypeError, json.JSONDecodeError):
        pass
    return []


# ====== K 线缓存(盘后预计算 日/周/月 + MA + KDJ) ======

def _build_cache_rows_for_code(grp, periods=('day', 'week', 'month')):
    """为单只股票计算各周期的 K 线 + MA + KDJ，返回可 executemany 的 tuple 列表。"""
    import numpy as np

    code = str(grp.iloc[0]['code'])
    all_rows = []

    for period_key in periods:
        if period_key == 'day':
            df = grp.copy()
        else:
            df = grp.set_index('date')
            df = df.resample('W' if period_key == 'week' else 'ME').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
                'amount': 'sum',
                'pre_close': 'last',
                'up': 'last',
            }).dropna(subset=['close']).reset_index()

        if df.empty:
            continue

        close = df['close'].values.astype(float)
        high = df['high'].values.astype(float)
        low = df['low'].values.astype(float)
        n = len(close)

        # MA 计算
        def _ma(arr, p):
            if n < p:
                return np.full(n, np.nan)
            result = np.full(n, np.nan)
            cumsum = np.cumsum(arr)
            result[p - 1:] = (cumsum[p - 1:] - np.concatenate([[0], cumsum[:-p]])) / p
            return result

        ma5 = _ma(close, 5)
        ma20 = _ma(close, 20)
        ma60 = _ma(close, 60)
        ma120 = _ma(close, 120)
        ma250 = _ma(close, 250)

        # KDJ 计算
        N = 9
        kdj_k = np.full(n, 50.0)
        kdj_d = np.full(n, 50.0)
        if n >= N:
            rsv = np.full(n, np.nan)
            for i in range(N - 1, n):
                ll = low[i - N + 1:i + 1].min()
                hh = high[i - N + 1:i + 1].max()
                rsv[i] = 50.0 if hh == ll else (close[i] - ll) / (hh - ll) * 100
            for i in range(1, n):
                if not np.isnan(rsv[i]):
                    kdj_k[i] = 2 / 3 * kdj_k[i - 1] + 1 / 3 * rsv[i]
                    kdj_d[i] = 2 / 3 * kdj_d[i - 1] + 1 / 3 * kdj_k[i]
        kdj_j = 3 * kdj_k - 2 * kdj_d

        def _clean(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            return round(float(v), 4)

        for i in range(n):
            row_date = df.iloc[i]['date']
            if hasattr(row_date, 'strftime'):
                row_date = row_date.strftime('%Y-%m-%d')
            else:
                row_date = str(row_date)[:10]

            pre_close_val = df.iloc[i].get('pre_close')
            up_val = df.iloc[i].get('up')

            all_rows.append((
                code, period_key, row_date,
                _clean(df.iloc[i]['open']),
                _clean(df.iloc[i]['high']),
                _clean(df.iloc[i]['low']),
                _clean(df.iloc[i]['close']),
                _clean(pre_close_val),
                int(df.iloc[i]['volume']) if not np.isnan(df.iloc[i]['volume']) else 0,
                _clean(df.iloc[i].get('amount', 0)),
                _clean(up_val),
                _clean(ma5[i]),
                _clean(ma20[i]),
                _clean(ma60[i]),
                _clean(ma120[i]),
                _clean(ma250[i]),
                _clean(kdj_k[i]),
                _clean(kdj_d[i]),
                _clean(kdj_j[i]),
            ))

    return all_rows


def build_kline_cache_batch(codes: List[str], periods: tuple = ('day', 'week', 'month')) -> int:
    """盘后批量建 K 线缓存: 对每只股票读 stock_daily,重采样,算 MA + KDJ,落 stock_kline_cache。"""
    import numpy as np
    df_all = get_daily_data_df(codes, days=700)
    if df_all is None or df_all.empty:
        return 0
    df_all = df_all.sort_values(['code', 'date']).reset_index(drop=True)
    total_written = 0
    for code, grp in df_all.groupby('code'):
        rows = _build_cache_rows_for_code(grp, periods)
        if not rows:
            continue
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM stock_kline_cache WHERE code = ?", (code,))
            cursor.executemany(
                """INSERT INTO stock_kline_cache
                (code, period, date, open, high, low, close, pre_close, volume, amount, up,
                 ma5, ma20, ma60, ma120, ma250, kdj_k, kdj_d, kdj_j)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        total_written += len(rows)
    return total_written


def get_kline_cache(code: str, period: str = 'day', tail: int = 60) -> Optional[Dict[str, Any]]:
    """从 stock_kline_cache 读取预计算 K 线(快路径),返回可以直接返回给前端的 dict。"""
    from data.store import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM stock_kline_cache WHERE code = ? AND period = ? ORDER BY date",
        (code, period),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([dict(r) for r in rows]).tail(tail)
    return {
        'code': code,
        'period': period,
        'data': [
            {
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': int(row.get('volume') or 0),
                'up': row.get('up', 0.0),
            }
            for _, row in df.iterrows()
        ],
        'ma5': [v for v in df['ma5'].tolist() if v is not None],
        'ma20': [v for v in df['ma20'].tolist() if v is not None],
        'ma60': [v for v in df['ma60'].tolist() if v is not None],
        'ma120': [v for v in df['ma120'].tolist() if v is not None],
        'ma250': [v for v in df['ma250'].tolist() if v is not None],
        'k': [v for v in df['kdj_k'].tolist() if v is not None],
        'd': [v for v in df['kdj_d'].tolist() if v is not None],
        'j': [v for v in df['kdj_j'].tolist() if v is not None],
    }


def get_template_screen_result_page(
    template_id: int,
    date: str = None,
    sort_by: str = 'change_pct',
    sort_order: str = 'desc',
    page: int = 1,
    page_size: int = 20,
    markets: List[str] = None,
    industries: List[str] = None,
    keyword: str = '',
    include_st: bool = False,
    exclude_suspended: bool = True,
) -> Dict[str, Any]:
    """从快照缓存表分页读取内置模板结果。"""
    sortable_columns = {
        'code', 'name', 'market', 'industry', 'listed_days', 'price', 'change',
        'change_pct', 'volume', 'amount', 'total_mv', 'circ_mv', 'pe_ttm', 'pb',
        'rps50', 'rps120', 'rps250',
    }
    order_column = sort_by if sort_by in sortable_columns else 'change_pct'
    order_direction = 'ASC' if str(sort_order).lower() == 'asc' else 'DESC'
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 20), 1)
    offset = (page - 1) * page_size

    params: List[Any] = [template_id]
    target_date = date
    with get_cursor() as cursor:
        if not target_date:
            cursor.execute(
                "SELECT MAX(date) FROM template_screen_cache WHERE template_id = ?",
                (template_id,),
            )
            row = cursor.fetchone()
            target_date = row[0] if row else None

        if not target_date:
            return {'date': '', 'items': [], 'total': 0}

        params.append(target_date)
        conditions = ["template_id = ?", "date = ?"]
        if markets:
            placeholders = ','.join('?' * len(markets))
            conditions.append(f"market IN ({placeholders})")
            params.extend(markets)
        if industries:
            placeholders = ','.join('?' * len(industries))
            conditions.append(f"industry IN ({placeholders})")
            params.extend(industries)
        if keyword:
            conditions.append("(code LIKE ? OR name LIKE ?)")
            like_value = f"%{keyword}%"
            params.extend([like_value, like_value])
        if not include_st:
            conditions.append("(name NOT LIKE '%ST%' AND name NOT LIKE '%*ST%')")
        if exclude_suspended:
            # 目前快照未持久化停牌字段，保持接口语义兼容。
            pass

        where_clause = " AND ".join(conditions)
        cursor.execute(
            f"SELECT COUNT(*) FROM template_screen_cache WHERE {where_clause}",
            params,
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT id, date, template_id, strategy_id, code, name,
                   market, industry, concept_tags, security_type, listed_date, listed_days,
                   price, change, change_pct, volume, amount, total_mv, circ_mv,
                   pe_ttm, pb, roe_ttm, revenue_yoy_q, net_profit_yoy_q,
                   rps50, rps120, rps250, reason, metadata
            FROM template_screen_cache
            WHERE {where_clause}
            ORDER BY {order_column} {order_direction}, id ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )
        rows = cursor.fetchall()

    items = []
    for row in rows:
        item = dict(row)
        item['metadata'] = _safe_json_loads(item.get('metadata'), {})
        item['concept_tags'] = _normalize_concept_tags({'concept_tags': item.get('concept_tags')})
        items.append(item)
    return {'date': target_date, 'items': items, 'total': total}


def get_screen_history(date: str = None, formula_id: int = None) -> List[Dict]:
    """获取历史选股结果"""
    conditions = []
    params = []
    
    if date:
        conditions.append("date = ?")
        params.append(date)
    if formula_id:
        conditions.append("formula_id = ?")
        params.append(formula_id)
    
    where = " AND ".join(conditions) if conditions else "1=1"
    
    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT sr.*, f.name as formula_name
            FROM screen_results sr
            LEFT JOIN formulas f ON sr.formula_id = f.id
            WHERE {where}
            ORDER BY sr.date DESC, sr.id
        """, params)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            if r.get('metadata'):
                r['metadata'] = json.loads(r['metadata'])
            results.append(r)
        return results


def get_latest_screen_results() -> Dict[int, List[Dict]]:
    """获取最新的选股结果，按公式分组"""
    with get_cursor() as cursor:
        # 获取每个公式的最新选股日期
        cursor.execute("""
            SELECT formula_id, MAX(date) as max_date
            FROM screen_results
            GROUP BY formula_id
        """)
        latest_dates = {row['formula_id']: row['max_date'] for row in cursor.fetchall()}
        
        if not latest_dates:
            return {}
        
        # 获取每个公式最新日期的选股结果
        results = {}
        for formula_id, max_date in latest_dates.items():
            cursor.execute("""
                SELECT sr.*, f.name as formula_name
                FROM screen_results sr
                LEFT JOIN formulas f ON sr.formula_id = f.id
                WHERE sr.formula_id = ? AND sr.date = ?
                ORDER BY sr.id
            """, (formula_id, max_date))
            rows = cursor.fetchall()
            stocks = []
            for row in rows:
                r = dict(row)
                if r.get('metadata'):
                    r['metadata'] = json.loads(r['metadata'])
                stocks.append(r)
            results[formula_id] = stocks
        
        return results


if __name__ == '__main__':
    init_db()
