"""定时任务 - 每日收盘后自动执行选股与数据更新"""
import sys
import os
from datetime import datetime, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import ScreeningEngine
from data.store import save_template_screen_results, get_stocks, get_formula_templates
from config import UPDATE_CONFIG
from strategies.b1_strategy import _ErrorCounter
from logger import get_logger

logger = get_logger(__name__)


def run_daily_screen():
    """每日收盘后执行选股"""
    logger.info(f"{datetime.now()} 开始执行每日选股...")
    
    try:
        engine = ScreeningEngine()

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
            print(
                f"[Scheduler] {strategy_id} 缓存快照完成: "
                f"{len(snapshot_items)}/{len(data.get('signals', []))} 只"
            )

        strategy_counts = {
            strategy_id: data.get('count', 0)
            for strategy_id, data in result.get('strategies', {}).items()
        }
        logger.info(f"选股完成: date={result.get('date')} counts={strategy_counts}")
        errors = _ErrorCounter.summary()
        if errors:
            logger.warning(f"选股过程中策略异常: {errors}")
        _ErrorCounter.reset()

    except Exception as e:
        logger.exception(f"执行失败: {e}")


def run_after_close_update():
    """盘后同步股票基础信息、更新日线、重建 RPS 和模板缓存。"""
    logger.info(f"{datetime.now()} 开始执行盘后更新...")

    try:
        from scripts_refresh_latest import refresh_daily_pipeline

        latest = refresh_daily_pipeline()
        logger.info(f"盘后更新完成: latest={latest}")

    except Exception as e:
        logger.exception(f"盘后更新失败: {e}")


def start_scheduler():
    """启动定时任务"""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()

    after_close_time = UPDATE_CONFIG.get('after_close', '20:00')
    daily_screen_time = UPDATE_CONFIG.get('daily_screen', '20:10')
    after_close_hour, after_close_minute = [int(part) for part in after_close_time.split(':', 1)]
    screen_hour, screen_minute = [int(part) for part in daily_screen_time.split(':', 1)]
    
    # 每日 20:10 执行选股，确保在盘后更新之后
    scheduler.add_job(
        run_daily_screen,
        'cron',
        hour=screen_hour,
        minute=screen_minute,
        id='daily_screen',
        replace_existing=True,
    )
    
    # 每日 20:00 执行盘后更新：同步 stock_basic + 更新日线 + RPS + 模板缓存
    scheduler.add_job(
        run_after_close_update,
        'cron',
        hour=after_close_hour,
        minute=after_close_minute,
        id='after_close_update',
        replace_existing=True,
    )
    
    scheduler.start()
    print('[Scheduler] 定时任务已启动')
    return scheduler


if __name__ == '__main__':
    scheduler = start_scheduler()
    
    # 保持运行
    import time
    while True:
        time.sleep(60)
