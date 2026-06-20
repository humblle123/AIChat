## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## 项目概述

Smart Stock Picker — 智能选股系统，面向个人投资者和量化爱好者的轻量级 A 股选股工具。一期支持类通达信公式编辑、内置策略模板（空谷幽兰 b1、月线反转 s2、RPS三线红 s3、一线红 kd1）、基础筛选（行业/概念/市值/涨跌幅等）、结果排序分页、股票详情页（K线/财务/技术指标）。数据源为腾讯财经（行情/K线）+ AKShare（财务/资料），每日盘后批量更新。

## 技术栈

- **后端**: Python 3.11, FastAPI, Uvicorn, SQLite, Pandas, NumPy, APScheduler, Pydantic
- **前端**: Vue 3 (Composition API), Pinia (状态管理), TailwindCSS, Vite, lightweight-charts (K线图)
- **数据**: 腾讯财经 API (实时行情/K线), AKShare (财务/基础资料), 通达信 .day 文件 (历史 K线)
- **部署**: Docker (Dockerfile.backend / Dockerfile.frontend), docker-compose, 看门狗脚本
- **测试**: pytest, pytest-asyncio, httpx

## 开发指令

### 后端
```bash
cd stock-picker
pip install -r requirements.txt
export PICKER_DB_DIR=/tmp/picker_db
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### 前端
```bash
cd stock-picker-vue
npm install
npm run dev  # 浏览器打开 http://localhost:5173
```

### 数据导入
```bash
# 1. 导入股票池(5500只)
python3 -c "import sys; sys.path.insert(0, 'stock-picker'); from data.fetcher import sync_stock_basic_from_local_cache; sync_stock_basic_from_local_cache('data/tencent_hs.json')"

# 2. 导入历史K线
python3 scripts/import_hsjday_to_sqlite.py  # ~3800万行

# 3. 重建RPS + 模板缓存
PICKER_DB_DIR=/tmp/picker_db python3 stock-picker/scripts_refresh_latest.py --rps-only
PICKER_DB_DIR=/tmp/picker_db python3 stock-picker/scripts_refresh_latest.py --cache-only
```

### 测试
```bash
cd stock-picker
PICKER_DB_DIR=/tmp python3 -m pytest tests/ -v  # 70 passed
```

### 性能测试
```bash
cd stock-picker
PICKER_DB_DIR=/tmp/picker_db python3 stock-picker/scripts/bench.py
```

## 架构和约束

### 目录结构
```
stock-system/
├── stock-picker/           # Python 后端
│   ├── app.py              # FastAPI 主入口(lifespan管理DB初始化+定时任务)
│   ├── config.py           # 配置(数据源/更新策略/策略参数)
│   ├── api/
│   │   ├── routes.py       # 6组REST端点(search/detail/kline/formula/templates/strategies)
│   │   └── schemas.py      # Pydantic 请求/响应模型
│   ├── data/
│   │   ├── store.py        # SQLite 数据访问层(连接池/WAL/schema迁移)
│   │   └── fetcher.py      # 腾讯财经/AKShare 数据采集
│   ├── engine/
│   │   ├── base.py         # ScreeningEngine 主类
│   │   ├── screening.py    # 选股主流程
│   │   ├── search.py       # 基础筛选
│   │   ├── detail.py       # 详情页构建
│   │   ├── kline.py        # K线(日/周/月重采样)
│   │   └── cache.py        # 模板缓存管理
│   ├── formula_engine.py   # 类通达信公式解析器(递归下降)
│   ├── indicators.py       # 向量化技术指标(MA/EMA/MACD/RSI/KDJ/HHV/LLV)
│   ├── strategies/         # 4个内置策略(b1/s2/s3/kd1)
│   ├── scheduler.py        # 盘后定时任务
│   └── logger.py           # 日志配置
├── stock-picker-vue/       # Vue 3 前端
│   ├── src/
│   │   ├── App.vue         # 主布局(选股页+详情页)
│   │   ├── stores/picker.js # Pinia 状态管理
│   │   ├── components/     # StockBoard / StockDetailPanel / KlineChart / StrategySidebar
│   │   └── lib/api.js      # API 请求封装
│   └── vite.config.js      # 代理 /api → backend:8080
├── scripts/                # 数据导入工具脚本
│   └── import_hsjday_to_sqlite.py  # 通达信 .day → SQLite
├── docker/
│   ├── entrypoint.sh       # 容器入口
│   └── watchdog.sh         # 看门狗
└── data/                   # 静态数据(tencent_hs.json 等)
```

### 架构决策
- **前后端分离**: Vue SPA + FastAPI REST，前端不直接调用第三方行情接口
- **SQLite 单机**: 一期无需分布式，数据文件 ~2.5-3GB。通过 PICKER_DB_DIR 环境变量切换路径
- **盘后批量更新**: 不做盘中实时刷新，APScheduler 定时在 20:00/20:10 执行
- **6组REST端点**: health / search / detail / kline / formula / templates/strategies
- **类通达信公式引擎**: 递归下降解析器 + 字段别名映射(CLOSE→close 等)，一期支持 MA/EMA/REF/COUNT/HHV/LLV/CROSS
- **向量化计算**: Pandas groupby/rolling/ewm 向量化，5481只 × 4策略 < 100ms
- **三级缓存**: 模板结果预计算入库 → 详情页走快路径 → 指标复用
- **公式引擎空值规则**: null 字段默认不命中数值比较条件

### 字段口径约束
- market 取值：SHA / SZA / CYB / KCB
- 估值：pe_ttm(滚动12月), pb, peg(pe_ttm/net_profit_yoy_q)
- 财务：roe_ttm, revenue_yoy_q, net_profit_yoy_q, debt_ratio
- 均线：ma5/10/20/60，基于最近 N 交易日收盘价均值
- MACD：固定参数 12,26,9
- RSI：固定参数 14，超买 70，超卖 30
- RPS：50/120/250 日收益率全市场百分位排名，每日盘后批量更新
- 所有字段以系统内部标准字段名输出，前端不感知第三方数据源差异

### 性能基准(已验证)
- 全市场模板筛选 5481只 × 4策略 < 100ms (目标 < 2s, 余量 20x)
- 单股详情页 43ms (目标 < 1s, 余量 23x)
- K线日/周/月 28-37ms (目标 < 1s)
- 公式引擎单只 2ms

## 当前任务

- P0 全部完成，P1 全部完成，P2 10/10 接近收尾
- 仅剩: P2-2 print 改 logging(~49 处，5 个文件: fetcher 11, store 1, scheduler 2, bench 17, refresh 18)
