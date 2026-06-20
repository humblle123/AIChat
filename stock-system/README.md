# Smart Stock Picker

智能选股系统 — 面向个人投资者的 A 股选股工具。

支持类通达信公式编辑、内置策略模板、基础筛选、结果排序分页、股票详情页（K 线/财务/技术指标）。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11, FastAPI, SQLite, Pandas |
| 前端 | Vue 3, Pinia, TailwindCSS, lightweight-charts |
| 数据 | 腾讯财经 + AKShare + 通达信 .day |
| 部署 | Docker Compose |

## 快速开始

```bash
# 1. 安装依赖
cd stock-picker && pip install -r requirements.txt
cd ../stock-picker-vue && npm install && cd ..

# 2. 导入数据
export PICKER_DB_DIR=/tmp/picker_db && mkdir -p $PICKER_DB_DIR
python3 -c "import sys; sys.path.insert(0, 'stock-picker'); from data.fetcher import sync_stock_basic_from_local_cache; sync_stock_basic_from_local_cache('data/tencent_hs.json')"
python3 scripts/import_hsjday_to_sqlite.py
PICKER_DB_DIR=/tmp/picker_db python3 stock-picker/scripts_refresh_latest.py --rps-only
PICKER_DB_DIR=/tmp/picker_db python3 stock-picker/scripts_refresh_latest.py --cache-only

# 3. 启动
cd stock-picker && PICKER_DB_DIR=/tmp/picker_db uvicorn app:app --host 0.0.0.0 --port 8080 &
cd ../stock-picker-vue && npm run dev
```

浏览器打开 http://localhost:5173

## 内置策略

| 策略 | 名称 | 核心逻辑 |
|------|------|----------|
| b1 | 空谷幽兰 | KDJ_J < 18 + 价格站上多空线 |
| s2 | 月线反转 | 站上年线 + 50日新高 + RPS50 ≥ 85 |
| s3 | RPS三线红 | RPS50 > 90 + RPS120 > 93 + RPS250 > 95 |
| kd1 | 一线红 | 任一RPS > 95 + 距高点 < 40% |

## 性能

| 指标 | 目标 | 实际 |
|------|------|------|
| 全市场筛选 5481 只 | < 2s | ~100ms |
| 单股详情页 | < 1s | ~43ms |
| K线日/周/月 | < 1s | 28-37ms |

## 文档

- [REQUIREMENTS.md](./REQUIREMENTS.md) — 完整需求规格
- [RUN.md](./RUN.md) — 本地运行指南
- [to_do_list.md](./to_do_list.md) — 优化待办清单
- [graphify-out/GRAPH_REPORT.md](./graphify-out/GRAPH_REPORT.md) — 知识图谱审计报告
