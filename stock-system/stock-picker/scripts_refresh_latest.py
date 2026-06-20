"""One-off refresh helpers for kline/RPS/template cache."""
import sys
import os
import argparse
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import RPS_PERIODS
from data.fetcher import get_kline, get_quote
from data.store import (
    get_stocks,
    get_daily_data_df,
    get_codes_needing_daily_update,
    save_daily_data,
    save_quote_snapshots,
    save_rps_data,
    get_formula_templates,
    save_template_screen_results,
)
from engine import ScreeningEngine
from logger import get_logger

logger = get_logger(__name__)


def rebuild_rps_from_price_frame(price_df: pd.DataFrame, latest_trade_date: str) -> int:
    """从收盘价透视表重建指定交易日的 RPS。"""
    rps_input = price_df.pivot(index='date', columns='code', values='close').sort_index()
    if rps_input.empty:
        return 0

    returns_map = {
        period: rps_input.pct_change(periods=period).iloc[-1].dropna()
        for period in RPS_PERIODS
    }

    valid_codes = 0
    for code in rps_input.columns:
        series = rps_input[code].dropna()
        if len(series) < max(RPS_PERIODS) + 1:
            continue

        rps_values = {}
        for period, latest_returns in returns_map.items():
            if code not in latest_returns.index or latest_returns.empty:
                rps_values[f'rps{period}'] = None
                continue
            rank = latest_returns.rank(method='average', pct=True).get(code)
            rps_values[f'rps{period}'] = round(float(rank) * 100, 4) if pd.notna(rank) else None

        if rps_values.get('rps250') is None:
            continue

        save_rps_data(code, latest_trade_date, rps_values)
        valid_codes += 1

    return valid_codes


def rebuild_rps_from_local_daily():
    """仅基于本地 stock_daily 重建最新交易日的 RPS。"""
    daily_df = get_daily_data_df(days=600)
    if daily_df is None or daily_df.empty:
        raise RuntimeError('本地 stock_daily 没有可用于重建 RPS 的数据')

    daily_df = daily_df.sort_values(['date', 'code']).reset_index(drop=True)
    latest_trade_date = daily_df['date'].max().strftime('%Y-%m-%d')
    valid_codes = rebuild_rps_from_price_frame(daily_df[['date', 'code', 'close']].copy(), latest_trade_date)
    print(f"[Refresh] RPS 重建完成: {valid_codes} 只，交易日: {latest_trade_date}")
    return latest_trade_date


def rebuild_template_cache_from_local_data():
    """仅基于本地 stock_daily / stock_rps 重新生成模板缓存。"""
    engine = ScreeningEngine()
    templates = get_formula_templates()
    template_map = {
        str(template.get('strategy_id', '')).lower(): template
        for template in templates
        if template.get('enabled', 1)
    }
    strategy_ids = [sid for sid in ['b1', 's2', 's3', 'kd1'] if sid in template_map]
    if not strategy_ids:
        raise RuntimeError('没有可用的策略模板')

    result = engine.screen(strategy_ids)
    refreshed = 0
    for strategy_id, data in result['strategies'].items():
        template = template_map.get(str(strategy_id).lower())
        if not template:
            continue
        snapshot_items = engine.build_template_result_snapshot(
            data.get('signals', []),
            int(template['id']),
            str(template['strategy_id']),
        )
        save_template_screen_results(
            result['date'],
            int(template['id']),
            str(template['strategy_id']),
            snapshot_items,
        )
        refreshed += 1
        print(f"[Refresh] {strategy_id} 模板缓存完成: {len(snapshot_items)} 只")

    print(f"[Refresh] 模板缓存重建完成: {refreshed} 个策略, date={result.get('date')}")
    return result.get('date')


def rebuild_rps_for_latest_date():
    stocks = get_stocks()
    codes = stocks['code'].astype(str).tolist()
    engine = ScreeningEngine()

    latest_frames = []
    updated_kline = 0
    for idx, code in enumerate(codes, start=1):
        if idx % 200 == 0:
            logger.info(f"K线进度 {idx}/{len(codes)}")
        df = get_kline(code, count=260)
        if df is None or df.empty:
            continue
        save_daily_data(code, df.to_dict('records'))
        latest_frames.append(df.assign(code=code))
        updated_kline += 1

    if not latest_frames:
        latest_df = get_daily_data_df(days=600)
        if latest_df is None or latest_df.empty:
            raise RuntimeError('未从本地或腾讯代理获取到任何K线数据')
    else:
        latest_df = pd.concat(latest_frames, ignore_index=True)
    latest_df = latest_df.sort_values(['date', 'code']).reset_index(drop=True)
    latest_trade_date = latest_df['date'].max().strftime('%Y-%m-%d')
    logger.info(f"最新交易日 {latest_trade_date}，成功更新K线 {updated_kline} 只")

    quotes = get_quote(codes)
    save_quote_snapshots(quotes, latest_trade_date)
    print(f"[Refresh] 行情快照更新完成: {len(quotes)} 只")

    _rebuild_rps_and_cache(engine, codes, latest_df, latest_trade_date)
    return latest_trade_date


def _rebuild_rps_and_cache(engine, codes, latest_df, latest_trade_date):
    """重建 RPS + 4 个内置策略的 template_screen_cache。"""
    valid_codes = rebuild_rps_from_price_frame(
        latest_df[['date', 'code', 'close']].copy(), latest_trade_date
    )
    logger.info(f"RPS 重建完成: {valid_codes} 只")

    templates = get_formula_templates()
    template_map = {
        str(template.get('strategy_id', '')).lower(): template
        for template in templates
        if template.get('enabled', 1)
    }
    strategy_ids = [sid for sid in ['b1', 's2', 's3', 'kd1'] if sid in template_map]
    result = engine.screen(strategy_ids)
    for strategy_id, data in result['strategies'].items():
        template = template_map.get(str(strategy_id).lower())
        if not template:
            continue
        try:
            snapshot_items = engine.build_template_result_snapshot(
                data.get('signals', []),
                int(template['id']),
                str(template['strategy_id']),
            )
            save_template_screen_results(
                latest_trade_date,
                int(template['id']),
                str(template['strategy_id']),
                snapshot_items,
            )
            print(f"[Refresh] {strategy_id} 模板缓存完成: {len(snapshot_items)} 只")
        except Exception as exc:
            logger.exception(f"{strategy_id} 模板缓存失败: {exc}")


def refresh_daily_pipeline():
    """盘后增量更新：先探测真实最新交易日，若本地数据落后则全量推进，随后重建 RPS 和模板缓存。"""
    stocks = get_stocks()
    codes = stocks['code'].astype(str).tolist()
    engine = ScreeningEngine()

    print(f"[Refresh] 开始盘后增量更新，共 {len(codes)} 只股票")
    from data.fetcher import batch_update_daily_data, get_quote, sync_stock_basic_from_local_cache, get_kline

    synced = sync_stock_basic_from_local_cache()
    print(f"[Refresh] stock_basic 同步完成: {synced} 只")

    # 1. 通过 API 探测真实最新交易日（取第一只股票 000001 的最近 K 线）
    real_latest = None
    probe = get_kline('000001', count=10)
    if probe is not None and not probe.empty:
        real_latest = probe['date'].max().strftime('%Y-%m-%d') if hasattr(probe['date'].max(), 'strftime') else str(probe['date'].max())
        print(f"[Refresh] API 探测最新交易日: {real_latest}")

    # 2. 查本地数据库最新交易日
    local_latest_df = get_daily_data_df(codes[:100], days=10)
    local_max_date = None
    if local_latest_df is not None and not local_latest_df.empty:
        local_max_date = local_latest_df['date'].max().strftime('%Y-%m-%d')
        print(f"[Refresh] 本地最新交易日: {local_max_date}")

    # 3. 决定更新策略
    if real_latest and local_max_date and real_latest > local_max_date:
        # 计算两个日期之间的自然日差值，加 3 天缓冲覆盖周末/节假日
        gap_days = (pd.to_datetime(real_latest) - pd.to_datetime(local_max_date)).days + 3
        print(f"[Refresh] 本地数据落后（{local_max_date} → {real_latest}），"
              f"需补齐约 {gap_days} 天数据，更新所有 {len(codes)} 只股票")
        updated = batch_update_daily_data(codes, days=gap_days, resume=True)
    else:
        # 本地数据已是最新 → 只补个别落后的股票
        reference_date = local_max_date
        target_codes = get_codes_needing_daily_update(reference_date, codes) if reference_date else codes
        print(f"[Refresh] 需要更新的股票: {len(target_codes)} 只")
        updated = batch_update_daily_data(target_codes, days=1, resume=True)

    print(f"[Refresh] 日线更新完成: {updated} 只")

    # 重建 K 线缓存（预计算 MA + KDJ）
    from data.store import build_kline_cache_batch
    print(f"[Refresh] 开始重建 K 线缓存...")
    cache_rows = build_kline_cache_batch(codes)
    print(f"[Refresh] K 线缓存重建完成: {cache_rows} 行")

    latest_df = get_daily_data_df(days=600)
    if latest_df is None or latest_df.empty:
        raise RuntimeError('本地 stock_daily 没有可用于重建 RPS 的数据')
    latest_df = latest_df.sort_values(['date', 'code']).reset_index(drop=True)
    latest_trade_date = latest_df['date'].max().strftime('%Y-%m-%d')
    print(f"[Refresh] 交易日: {latest_trade_date}")

    quotes = get_quote(codes)
    save_quote_snapshots(quotes, latest_trade_date)
    print(f"[Refresh] 行情快照更新完成: {len(quotes)} 只")

    _rebuild_rps_and_cache(engine, codes, latest_df, latest_trade_date)

    print(f"[Refresh] 盘后增量更新完成，最新交易日: {latest_trade_date}")
    return latest_trade_date


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rps-only', action='store_true', help='only rebuild latest-date RPS from local stock_daily')
    parser.add_argument('--cache-only', action='store_true', help='only rebuild template cache from local stock_daily/rps')
    parser.add_argument('--daily-update', action='store_true', help='run after-close incremental daily update')
    parser.add_argument('--full-refresh', action='store_true', help='full refresh by refetching kline data for all stocks')
    args = parser.parse_args()

    if args.cache_only:
        latest = rebuild_template_cache_from_local_data()
    elif args.rps_only:
        latest = rebuild_rps_from_local_daily()
    elif args.daily_update:
        latest = refresh_daily_pipeline()
    elif args.full_refresh:
        latest = rebuild_rps_for_latest_date()
    else:
        latest = refresh_daily_pipeline()
    print(f"[Refresh] 完成，最新交易日: {latest}")
