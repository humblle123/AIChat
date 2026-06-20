#!/bin/bash
# 不用 set -e，避免非关键步骤失败导致容器无法启动
# 关键步骤（建表、导入）通过 if 显式处理错误

# ============================================
# Smart Stock Picker - 数据初始化入口脚本
# ============================================
# 首次启动时自动检测数据库是否已初始化，
# 若为空则依次执行：股票池导入 → K 线导入 → RPS 重建 → 模板缓存重建

DB_FILE="${PICKER_DB_DIR:-/app/data}/stocks.db"
INIT_FLAG="${PICKER_DB_DIR:-/app/data}/.initialized"

echo "[Entrypoint] =========================================="
echo "[Entrypoint] Smart Stock Picker 启动中..."
echo "[Entrypoint] DB_PATH: $DB_FILE"
echo "[Entrypoint] =========================================="

# 确保数据目录存在
mkdir -p "${PICKER_DB_DIR:-/app/data}"

if [ -f "$INIT_FLAG" ]; then
    echo "[Entrypoint] 数据库已初始化过，跳过数据导入。"
else
    echo "[Entrypoint] 首次启动，开始数据初始化..."

    # Step 0: 初始化数据库表结构（必须先建表，后续导入才能查询）
    echo "[Entrypoint] [0/4] 初始化数据库表结构..."
    cd /app/stock-picker
    python3 -c "
import sys; sys.path.insert(0, '.')
from data.store import init_db
init_db()
print('[Entrypoint] 数据库表结构创建完成')
"

    # Step 1: 导入股票池（从 tencent_hs.json 同步 ~5500 只 A 股）
    echo "[Entrypoint] [1/4] 导入股票池..."
    if [ -f "/app/data/tencent_hs.json" ]; then
        cd /app/stock-picker
        python3 -c "
import sys; sys.path.insert(0, '.')
from data.fetcher import sync_stock_basic_from_local_cache
n = sync_stock_basic_from_local_cache('/app/data/tencent_hs.json')
print(f'[Entrypoint] 导入 {n} 只股票')
"
    else
        echo "[Entrypoint] 警告: /app/data/tencent_hs.json 不存在，跳过股票池导入"
    fi

    # Step 2: 导入历史 K 线（从通达信 .day 文件，约 3800 万行，2-5 分钟）
    echo "[Entrypoint] [2/4] 导入历史 K 线（可能需要 2-5 分钟）..."
    if [ -d "/app/hsjday 2/sh" ] || [ -d "/app/hsjday 2/sz" ]; then
        cd /app
        PICKER_DB_DIR="${PICKER_DB_DIR:-/app/data}" python3 scripts/import_hsjday_to_sqlite.py
    else
        echo "[Entrypoint] 警告: /app/hsjday 2/ 目录不存在，跳过 K 线导入"
    fi

    # Step 3: 重建 RPS（50/120/250 日相对强弱排名）
    echo "[Entrypoint] [3/4] 重建 RPS 排名（可能需要 1-3 分钟）..."
    cd /app/stock-picker
    if PICKER_DB_DIR="${PICKER_DB_DIR:-/app/data}" python3 scripts_refresh_latest.py --rps-only; then
        echo "[Entrypoint] RPS 重建成功"
    else
        echo "[Entrypoint] 警告: RPS 重建失败（可能内存不足），后端定时任务会在 20:00 自动重试"
    fi

    # Step 4: 重建模板缓存（跑 b1/s2/s3/kd1 4 个策略）
    echo "[Entrypoint] [4/4] 重建模板缓存..."
    if PICKER_DB_DIR="${PICKER_DB_DIR:-/app/data}" python3 scripts_refresh_latest.py --cache-only; then
        echo "[Entrypoint] 模板缓存重建成功"
    else
        echo "[Entrypoint] 警告: 模板缓存重建失败，后端定时任务会在 20:10 自动重试"
    fi

    # 标记初始化完成
    touch "$INIT_FLAG"
    echo "[Entrypoint] 数据初始化完成！"
fi

echo "[Entrypoint] 启动后端服务: $@"
cd /app/stock-picker
exec "$@"
