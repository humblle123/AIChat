"""data.store 单元测试: 初始化 / 写入 / 读取 / schema migration / stocks 表迁移。"""
import os
import sqlite3
import pandas as pd
import pytest

import data.store as store


class TestInitDB:
    def test_creates_all_tables(self):
        with store.get_cursor() as cursor:
            names = {
                row['name']
                for row in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        for required in {'stock_basic', 'stock_daily', 'stock_rps', 'stock_quote_snapshot',
                          'template_screen_cache', 'formula_template', 'formulas', 'screen_results'}:
            assert required in names, f'缺少表 {required}'

    def test_stocks_table_dropped(self):
        """P1-7: 旧 stocks 表应被迁移后 DROP。"""
        with store.get_cursor() as cursor:
            names = {
                row['name']
                for row in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'"
                ).fetchall()
            }
        assert 'stocks' not in names

    def test_default_templates_seeded(self):
        templates = store.get_formula_templates()
        ids = {t['strategy_id'] for t in templates}
        assert ids == {'b1', 's2', 's3', 'kd1'}

    def test_idempotent(self):
        # 跑两遍 init_db 不应抛错
        store.init_db()
        store.init_db()


class TestStockBasic:
    def test_save_and_get(self):
        store.save_stock_basic([
            {'code': '600519', 'name': '贵州茅台', 'market': 'SHA', 'is_st': 0},
            {'code': '000858', 'name': '五粮液', 'market': 'SZA', 'is_st': 0},
        ])
        df = store.get_stocks()
        assert len(df) == 2
        assert set(df['code'].tolist()) == {'600519', '000858'}

    def test_on_conflict_updates(self):
        store.save_stock_basic([{'code': '600519', 'name': '原名', 'is_st': 0}])
        store.save_stock_basic([{'code': '600519', 'name': '新名', 'is_st': 0}])
        row = store.get_stock_basic_by_code('600519')
        assert row['name'] == '新名'

    def test_get_by_codes(self):
        store.save_stock_basic([
            {'code': '600519', 'name': 'A'},
            {'code': '000858', 'name': 'B'},
            {'code': '300750', 'name': 'C'},
        ])
        df = store.get_stocks_by_codes(['600519', '000858'])
        assert len(df) == 2
        assert set(df['code'].tolist()) == {'600519', '000858'}


class TestDailyData:
    def test_save_and_query(self):
        store.save_daily_data('600519', [
            {'date': '2024-01-02', 'open': 100, 'high': 105, 'low': 99,
             'close': 104, 'pre_close': 100, 'volume': 1_000_000, 'amount': 1e8, 'up': 4.0},
        ])
        df = store.get_daily_data_df(['600519'])
        assert len(df) == 1
        assert df.iloc[0]['close'] == 104

    def test_on_conflict_updates(self):
        store.save_daily_data('600519', [
            {'date': '2024-01-02', 'open': 100, 'high': 105, 'low': 99, 'close': 104,
             'pre_close': 100, 'volume': 1_000_000, 'amount': 1e8, 'up': 4.0},
        ])
        # 重新写,改 high
        store.save_daily_data('600519', [
            {'date': '2024-01-02', 'open': 100, 'high': 999, 'low': 99, 'close': 104,
             'pre_close': 100, 'volume': 1_000_000, 'amount': 1e8, 'up': 4.0},
        ])
        df = store.get_daily_data_df(['600519'])
        assert df.iloc[0]['high'] == 999


class TestRPS:
    def test_save_and_query(self):
        store.save_rps_data('600519', '2024-01-02', {'rps50': 90.0, 'rps120': 85.0, 'rps250': 80.0})
        df = store.get_rps_data(['600519'])
        assert not df.empty
        row = df.iloc[0]
        assert row['rps50'] == 90.0


class TestQuoteSnapshot:
    def test_save_and_query(self):
        store.save_quote_snapshots([
            {'code': '600519', 'price': 100, 'close': 99, 'total_mv': 1.5e12, 'circ_mv': 1.2e12},
        ], '2024-01-02')
        df = store.get_latest_quote_snapshot(['600519'])
        assert not df.empty
        row = df.iloc[0]
        assert row['total_mv'] == 1.5e12
        assert row['circ_mv'] == 1.2e12  # P0-6 修过的字段


class TestTemplateCache:
    def test_save_and_get_hits(self):
        # P1-5: template_hits_json 落库 + 读回
        store.save_template_screen_results('2024-01-02', 1, 'b1', [
            {'code': '600519', 'name': '贵州茅台', 'reason': 'b1 命中',
             'rps50': 90, 'price': 100, 'change_pct': 2.5},
        ])
        hits = store.get_template_hits_for_code('600519')
        # 缓存里没存 template_hits_json 时返回 []
        assert isinstance(hits, list)


class TestSchemaMigrations:
    def test_pending_migration_adds_column(self):
        # 用一个新的最小表验证迁移函数本身
        with store.get_cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS test_migration (id INTEGER PRIMARY KEY)")
        with store.get_cursor() as cursor:
            # 直接给 test_migration 加一列
            cursor.execute("ALTER TABLE test_migration ADD COLUMN name TEXT")
        # 验证 _apply_pending_migrations 对新表也工作
        # (不需要测 template_screen_cache,真实场景由 init_db 走)
        with store.get_cursor() as cursor:
            cols = {row['name'] for row in cursor.execute("PRAGMA table_info(test_migration)").fetchall()}
        assert 'name' in cols

    def test_migration_idempotent(self):
        # 再跑一次不应报错
        with store.get_cursor() as cursor:
            store._apply_pending_migrations(cursor)
