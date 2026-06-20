"""性能回归测试 bench.py。

衡量三项关键指标(对齐 REQUIREMENTS.md 9.1):
  - 单次 /api/stocks/template-results 模板 3 (s3) 全市场 < 2s
  - 单股详情页 /api/stocks/{code} < 1s
  - 单股 K 线 /api/kline/{code} 日/周/月 各自 < 1s

用法:
  PICKER_DB_DIR=/path/to/db python3 scripts/bench.py [--samples N] [--stock 000001]

注意: 这是 benchmark,不是单元测试。结果会随数据规模变化。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def time_it(label: str, fn, repeat: int = 3) -> tuple[float, list[float]]:
    """跑 fn repeat 次,返回 (中位数毫秒, 每次毫秒列表)。"""
    samples = []
    for i in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        dt = (time.perf_counter() - t0) * 1000
        samples.append(dt)
        extra = '' if result is None else f' (result={result})'
        print(f'  {label:<40s} run {i+1}/{repeat}: {dt:7.1f} ms{extra}')
    median = statistics.median(samples)
    print(f'  {label:<40s} median: {median:7.1f} ms (min={min(samples):.0f} max={max(samples):.0f})')
    return median, samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=3, help='每项指标重复次数')
    parser.add_argument('--stock', default='000001', help='详情/K 线测试用的 stock code')
    parser.add_argument('--periods', default='day,week,month', help='K 线测试的 period 列表(逗号分隔)')
    args = parser.parse_args()

    from data.store import (
        get_stocks, get_daily_data_df, get_rps_data, init_db,
        get_formula_templates, get_stock_basic_by_code, get_latest_quote_snapshot,
    )
    from engine import ScreeningEngine
    from api.routes import engine as routes_engine

    init_db()
    stock_df = get_stocks()
    print(f'== benchmark: stock_basic {len(stock_df)} rows ==\n')

    codes = stock_df['code'].astype(str).tolist()
    targets = {
        'PASS_2s': 2000.0,
        'PASS_1s': 1000.0,
    }

    # ====== 1. 单只详情页 ======
    print('== 1. /api/stocks/{code} 详情页 ==')
    median, _ = time_it(
        f'GET /api/stocks/{args.stock}',
        lambda: routes_engine.get_stock_detail(args.stock),
        repeat=args.samples,
    )
    print(f'  目标 < 1000ms, 实际 {median:.0f}ms  -> {"PASS" if median < 1000 else "FAIL"}\n')

    # ====== 2. 单股 K 线 ======
    print('== 2. /api/kline/{code} 各 period ==')
    for period in args.periods.split(','):
        median, _ = time_it(
            f'GET /api/kline/{args.stock}?period={period}',
            lambda p=period: routes_engine.get_kline(args.stock, p),
            repeat=args.samples,
        )
        print(f'  目标 < 1000ms, 实际 {median:.0f}ms  -> {"PASS" if median < 1000 else "FAIL"}')
    print()

    # ====== 3. 全市场模板结果 ======
    # 用 s3 (template_id 3) 做代表,因为它要扫全市场 + JOIN RPS,最重
    print('== 3. /api/stocks/template-results 模板 3 (s3 RPS三线红) ==')
    from api.schemas import StockSearchRequest
    request = StockSearchRequest(
        template_id=3, page=1, page_size=20, sort_by='change_pct', sort_order='desc',
    )

    # 先 warm up(让 SQLite 准备好缓存,避免第一次冷启动拉偏)
    routes_engine.get_cached_template_results(request.dict())

    median, _ = time_it(
        'POST /api/stocks/template-results {s3, page=1}',
        lambda: routes_engine.get_cached_template_results(request.dict()),
        repeat=args.samples,
    )
    # 注意:这是缓存读,不是 5000 只实时筛选的端到端时间
    print(f'  缓存读 < 1000ms 目标, 实际 {median:.0f}ms  -> {"PASS" if median < 1000 else "FAIL"}\n')

    # ====== 4. 全市场端到端 screen 性能(走完整个 pipeline) ======
    print('== 4. engine.screen(["s3"]) 全市场 端到端 ==')
    e = ScreeningEngine()
    # warm up
    try:
        e.screen(['s3'])
    except Exception as e:
        pass

    median, _ = time_it(
        'engine.screen(["s3"]) on 全市场',
        lambda: e.screen(['s3']),
        repeat=args.samples,
    )
    print(f'  目标 < 2000ms, 实际 {median:.0f}ms  -> {"PASS" if median < 2000 else "FAIL"}\n')

    # ====== 5. 公式引擎单只评估 ======
    print('== 5. formula_engine.evaluate_formula b1 公式 (单只) ==')
    from formula_engine import evaluate_formula
    daily_df = get_daily_data_df([args.stock], days=600)
    if daily_df is not None and not daily_df.empty:
        rps_df = get_rps_data([args.stock])
        scalars = rps_df.iloc[0].to_dict() if rps_df is not None and not rps_df.empty else {}
        b1_expr = (
            'ZXDQ := EMA(EMA(CLOSE, 10), 10); '
            'ZXDKX := (MA(CLOSE, 14) + MA(CLOSE, 28) + MA(CLOSE, 57) + MA(CLOSE, 114)) / 4; '
            'KDJ_J < 18 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX'
        )
        median, _ = time_it(
            f'evaluate b1 on {args.stock}',
            lambda: evaluate_formula(b1_expr, daily_df, scalars),
            repeat=args.samples,
        )
        print(f'  目标 < 100ms (单只), 实际 {median:.0f}ms  -> {"PASS" if median < 100 else "FAIL"}\n')

    print('== 总结 ==')
    print('  各项指标对照 REQUIREMENTS.md 9.1 性能目标。')
    print('  数据规模对结果影响大,小数据集(< 100 只)数值仅供参考。')


if __name__ == '__main__':
    main()
