# Smart Stock Picker 系统工作流文档

> 版本: 1.0 | 更新: 2026-06-18 | 测试: 70 个 pytest 全过

---

## 目录

1. [架构总览](#1-架构总览)
2. [数据流全景](#2-数据流全景)
3. [模块职责](#3-模块职责)
4. [数据 Pipeline](#4-数据-pipeline)
5. [配置与环境变量](#5-配置与环境变量)
6. [公式引擎](#6-公式引擎)
7. [缓存体系](#7-缓存体系)
8. [API 文档](#8-api-文档)
9. [前端交互](#9-前端交互)
10. [调度与维护](#10-调度与维护)
11. [性能指标](#11-性能指标)

---

## 1. 架构总览

```
用户浏览器 (stock-picker-vue)
       │  HTTP/JSON
       ▼
  FastAPI (uvicorn :8080)
       │
       ├── /api/formula/templates     ← 内置策略模板 (b1/s2/s3/kd1)
       ├── /api/formula/validate      ← 公式校验
       ├── /api/stocks/search         ← 股票搜索 (基础筛选 + 公式)
       ├── /api/stocks/template-results ← 模板结果 (走缓存)
       ├── /api/stocks/template-summary  ← 模板命中摘要
       ├── /api/stocks/{code}         ← 股票详情
       ├── /api/kline/{code}          ← K 线 (日/周/月, 优先缓存)
       ├── /api/screen                ← 选股 (4 策略并行)
       ├── /api/strategies            ← 策略列表
       ├── /api/health /live /ready   ← K8s 探针
       └── /openapi.json              ← Swagger 文档
              │
              ▼
        ScreeningEngine (mixin 多继承)
       ┌──────────────────────────────────┐
       │ engine.screening  → screen()     │
       │ engine.search     → search()     │
       │ engine.detail     → get_stock_detail() │
       │ engine.kline      → get_kline()  │
       │ engine.cache      → get_cached_template_results() │
       │ formula_engine    → evaluate_formula() │
       │ indicators        → compute_ma/ema/kdj/macd/rsi │
       └──────────────────────────────────┘
              │
              ▼
         SQLite (长连接 + WAL)
       ┌──────────────────────────────────┐
       │ stock_basic       → 5500 只股票基础信息     │
       │ stock_daily       → 日线 OHLCVA (~3800万行) │
       │ stock_kline_cache → K 线缓存 (日/周/月+MA+KDJ) │
       │ stock_quote_snapshot → 行情快照             │
       │ stock_rps         → RPS 预计算              │
       │ template_screen_cache → 模板命中缓存        │
       │ formula_template  → 内置策略模板            │
       │ formulas          → 用户自定义公式           │
       │ screen_results    → 选股结果历史             │
       └──────────────────────────────────┘
              │
              ▼
         数据源 (fetcher.py)
       ┌──────────────────────────────────┐
       │ 腾讯财经 qt.gtimg.cn  → 实时行情   │
       │ 腾讯财经 proxy.finance.qq.com → K 线 │
       │ 通达信 .day 文件 (hsjday 2/) → 历史日线 │
       │ tencent_hs.json → 全 A 股票池(5524 只) │
       └──────────────────────────────────┘
              │
              ▼
       APScheduler (定时任务 :8080 进程内)
       ┌──────────────────────────────────┐
       │ 20:00 → run_after_close_update   │
       │ 20:10 → run_daily_screen         │
       └──────────────────────────────────┘
```

---

## 2. 数据流全景

### 2.1 数据流向图

```
┌─────────────────────────────────────────────────────────────────┐
│                      初始化阶段 (一次性)                          │
│                                                                   │
│  tencent_hs.json ──→ sync_stock_basic_from_local_cache()          │
│                        ↓                                          │
│                   stock_basic 表 (5500 只 → 5481 只过滤后)        │
│                                                                   │
│  .day 文件 ──→ import_hsjday_to_sqlite.py                         │
│               (多线程解析 + 单连接 upsert)                         │
│                        ↓                                          │
│                   stock_daily 表 (~3800万行)                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      盘后更新阶段 (每日)                           │
│                                                                   │
│  refresh_daily_pipeline():                                        │
│    1. sync_stock_basic_from_local_cache()  ← 更新股票基础信息     │
│    2. batch_update_daily_data(today)       ← 拉最新 1 天 K 线    │
│    3. rebuild_rps_from_price_frame()       ← 重建 RPS            │
│    4. get_quote() → save_quote_snapshots() ← 行情快照            │
│    5. _rebuild_rps_and_cache()             ← 重建模板缓存         │
│       ├── engine.screen([b1,s2,s3,kd1])   ← 跑 4 个策略         │
│       └── build_template_result_snapshot() ← 评估 4 模板命中      │
│           └── save_template_screen_results() ← 落 template_screen_cache │
│    6. build_kline_cache_batch()             ← 重建 K 线缓存      │
│       └── 对每只 stock_daily 重采样周/月 + 算 MA/KDJ             │
│           └── write stock_kline_cache                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       查询阶段 (实时)                              │
│                                                                   │
│  请求 /api/stocks/search                                          │
│    ↓                                                              │
│  engine.search()                                                  │
│    ├── _apply_search_filters()  ← stock_basic 基础筛选            │
│    ├── template? → 读 template_screen_cache                      │
│    ├── formula?  → formula_engine.evaluate_formula()             │
│    └── _enrich_search_results()  ← JOIN stock/rps/daily          │
│                                                                   │
│  请求 /api/stocks/{code}                                          │
│    ↓                                                              │
│  engine.get_stock_detail()                                        │
│    ├── get_stock_basic_by_code()  ← stock_basic                  │
│    ├── get_daily_data_df()        ← stock_daily                  │
│    ├── get_latest_quote_snapshot() ← stock_quote_snapshot        │
│    ├── get_rps_data()             ← stock_rps                    │
│    ├── _build_detail_technicals() ← indicators.py 一次性向量化   │
│    └── _build_template_hits()     ← 优先读 template_hits_json    │
│         └── get_template_hits_for_code() ← 快路径缓存            │
│                                                                   │
│  请求 /api/kline/{code}?period=day|week|month                     │
│    ↓                                                              │
│  engine.get_kline()                                               │
│    ├── get_kline_cache()  ← stock_kline_cache (快路径)           │
│    │   命中? → 直接返回 pre-joined MA/KDJ                         │
│    └── 未命中? → get_daily_data_df() + resample + 实时算 MA/KDJ  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 各个表的行数和关系

| 表名 | 行数(约) | 用途 | 更新频率 |
|------|---------|------|---------|
| stock_basic | 5,481 | 股票代码/名称/市场/行业/ST/停牌 | 每日 |
| stock_daily | ~38,000,000 | 日线 OHLCVA (open/high/low/close/volume/amount) | 每日增量 upsert |
| stock_kline_cache | ~1,800,000 | 日/周/月 K + MA5/20/60/120/250 + KDJ | 每日全量重建(盘后) |
| stock_quote_snapshot | 5,481 | 最新行情快照: price/change/pct/total_mv/circ_mv | 每日覆盖 |
| stock_rps | 5,481 | RPS50/120/250 (全市场排名) | 每日全量重建 |
| template_screen_cache | ~500-2000 | 4 模板命中明细 + template_hits_json (所有模板命中的 4 模板评估) | 每日覆盖 |
| formula_template | 4 | 内置策略模板定义 | 静态 |
| formulas | 4 | 用户自定义公式(预留) | 手动 |

---

## 3. 模块职责

### 3.1 stock-picker/engine/ (主引擎 — mixin 拆分后)

| 文件 | 类/函数 | 职责 |
|------|---------|------|
| `base.py` | `ScreeningEngine` | 公共工具: `_safe_float / _format_date / _parse_concepts / _empty_search_result` |
| `screening.py` | `ScreeningMixin` | `screen(strategies)` → 4 策略全市场选股; `_prefilter_for_strategy` → RPS 预筛选; `build_template_result_snapshot` → 盘后缓存落库 |
| `search.py` | `SearchMixin` | `search(request)` → 基础筛选 + 公式搜索; `_evaluate_formula_search` → 公式引擎 real-time; `_enrich_search_results` → 字段富化 + Pydantic 校验 |
| `detail.py` | `DetailMixin` | `get_stock_detail(code)` → 详情页聚合; `_build_detail_quote/technicals/kline` → 行情/技术指标/K 线摘要; `_build_template_hits` → 快路径读缓存 |
| `kline.py` | `KLineMixin` | `get_kline(code, period)` → 日/周/月 K; 优先 `get_kline_cache` → 降级实时重采样 + MA/KDJ |
| `cache.py` | `CacheMixin` | `get_cached_template_results` → 模板预计算缓存读取,支持分页/排序/筛选 |

### 3.2 stock-picker/strategies/ (内置策略)

| 文件 | 策略 | 核心逻辑 |
|------|------|---------|
| `b1_strategy.py` | 空谷幽兰 | KDJ_J<18 AND close>EMA10 AND EMA10>多空线均线平均 |
| `s2_strategy.py` | 月线反转 | close>MA250 AND 30日内创50日新高 AND RPS50>=85 AND 站年线2~30天 |
| `s3_strategy.py` | RPS三线红 | RPS50>90 AND RPS120>93 AND RPS250>95 AND close/HHV250>0.85 |
| `kd1_strategy.py` | 一线红 | (RPS>95 任一) AND close/HHV250>0.6 |

所有策略都已向量化: 对 `daily_data` 一次性 `groupby + rolling/ewm` 算指标,不再逐股 for 循环。异常通过 `_ErrorCounter` 计数,不静默吞。

### 3.3 stock-picker/data/ (数据层)

| 文件 | 职责 |
|------|------|
| `store.py` | SQLite 核心: 长连接单例(`check_same_thread=False`)、WAL 模式(失败自动降级)、集中式 `SCHEMA_MIGRATIONS`(新字段一行加)、8 张表的 CRUD、`build_kline_cache_batch / get_kline_cache` |
| `fetcher.py` | 数据源: 腾讯 `qt.gtimg.cn` 行情(50 只/批 + 并发)、腾讯 `proxy.finance.qq.com` K 线(260 根/请求)、`batch_update_daily_data` (ThreadPoolExecutor 4-8 线程)、`sync_stock_basic_from_local_cache`(从本地 json 同步股票池) |

### 3.4 stock-picker/formula_engine.py (公式引擎)

**独立模块**: 不依赖 FastAPI/engine/策略。

支持:
- 词法分析 → AST 组合 → 递归求值
- 字段别名: `CLOSE → close`, `KDJ_J → kdj_j`, `RPS50 → rps50` 等
- 逻辑: `AND / OR / NOT`
- 比较: `> >= < <= = !=`
- 算术: `+ - * /` + 括号
- 函数: `MA / EMA / REF / COUNT / HHV / LLV / CROSS`
- 变量: `:=` 定义, `;` 分隔
- 空值规则: `peg=null` 时 `peg < 1` → `false`

两个入口:
- `evaluate_formula(expr, daily_df, scalars)` → 对单只股票求值,返回 `(hit:bool, info:dict)`
- `validate(formula)` → 返回 `{valid, errors, used_fields, normalized_formula}`

### 3.5 stock-picker/indicators.py (指标引擎)

**独立模块**: 不依赖 FastAPI/engine/策略。

对全市场 DataFrame (`code, date, open, high, low, close, volume`) 一次性算出:
- `compute_ma` → MA5/10/20/60/120/250
- `compute_ema` → EMA10/12/26
- `compute_macd` → MACD(12,26,9)
- `compute_rsi` → RSI(14)
- `compute_kdj` → KDJ(9,3,3) — 用 `max(high, close)` 和 `min(low, close)` 联合避免 RSV 越界
- `compute_hhv` → HHV(50/100/250)

### 3.6 stock-picker/api/ (API 层)

| 文件 | 职责 |
|------|------|
| `routes.py` | 9 个路由(endpoint),用 `ScreeningEngine` 实例 |
| `schemas.py` | Pydantic 模型(请求/响应) + OpenAPI tags 定义 |

### 3.7 脚本工具

| 文件 | 用途 |
|------|------|
| `scripts/import_hsjday_to_sqlite.py` | 一次性导入: 多线程解析 `.day` 文件 → 单连接 execmany upsert |
| `scripts_refresh_latest.py` | 盘后更新: `--rps-only` / `--cache-only` / `--daily-update` / `--full-refresh` |
| `stock-picker/scripts/bench.py` | 性能回归: 详情页 / K 线(3 周期) / 模板结果 / screen / 公式引擎 |

### 3.8 前端 stock-picker-vue/

| 文件 | 职责 |
|------|------|
| `src/App.vue` | 主布局: 策略侧边栏(K 线图表 + 股票列表 + 详情面板) |
| `src/stores/picker.js` | Pinia store: 模板加载 → 选中 → 结果展示 → 详情缓存,带 mock 兜底 |
| `src/lib/api.js` | API 客户端: 5 个端点(templates / summary / results / stock detail / kline) |
| `src/components/KlineChart.vue` | 图表: lightweight-charts v4,日/周/月切换,MA5-250 + KDJ 子图 |
| `src/components/StockDetailPanel.vue` | 详情面板: 行情/财务/技术指标卡片 |
| `src/components/StrategySidebar.vue` | 侧边栏: 4 个模板选择 + 命中数量 |

---

## 4. 数据 Pipeline

### 4.1 初始化(全新部署)

```bash
# 1. 安装依赖
cd stock-picker && pip install -r requirements.txt
cd ../stock-picker-vue && npm install

# 2. 配置数据库路径
export PICKER_DB_DIR=/tmp/picker_db
mkdir -p $PICKER_DB_DIR

# 3. 导入股票基础信息 (stock_basic)
python3 -c "
import sys; sys.path.insert(0,'stock-picker')
from data.fetcher import sync_stock_basic_from_local_cache
n = sync_stock_basic_from_local_cache('data/tencent_hs.json')
print(f'导入 {n} 只 A 股')
"

# 4. 导入历史日线 (stock_daily)
PICKER_DB_DIR=/tmp/picker_db python3 scripts/import_hsjday_to_sqlite.py
# → 读取 hsjday 2/{sh,sz}/lday/*.day
# → 多线程解析 32 字节二进制格式
# → 单连接 upsert stock_daily

# 5. 重建 RPS (stock_rps)
cd stock-picker
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --rps-only
# → 从 stock_daily 读 600 天全部收盘价
# → pivot 成 (date × code) 矩阵
# → pct_change 算 50/120/250 日收益率
# → rank(pct=True) * 100 → RPS ∈ [0,100]

# 6. 重建模板缓存 (template_screen_cache)
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --cache-only
# → engine.screen(['b1','s2','s3','kd1'])
# → 对每个命中的股票跑 formula_engine.evaluate_formula() 评估 4 模板
# → 结果写入 template_screen_cache.template_hits_json

# 7. 可选: K 线缓存 (stock_kline_cache)
PICKER_DB_DIR=/tmp/picker_db python3 -c "
import sys; sys.path.insert(0,'.')
from data.store import build_kline_cache_batch, get_stocks
codes = get_stocks()['code'].astype(str).tolist()
build_kline_cache_batch(codes)
"
```

### 4.2 每日盘后更新

```bash
# 盘后一键更新 (APScheduler 自动执行,也可手动)
cd stock-picker
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --daily-update
```

该命令依次执行:
1. `sync_stock_basic_from_local_cache()` — stock_basic 同步
2. `batch_update_daily_data(today)` — 并发拉今天 1 根 K 线
3. `rebuild_rps_from_price_frame()` — 全市场 RPS 重建
4. `get_quote() → save_quote_snapshots()` — 行情快照
5. `engine.screen() → build_template_result_snapshot() → save_template_screen_results()` — 模板缓存
6. **不包含** `build_kline_cache_batch` — K 线缓存需手动触发

### 4.3 启动服务

```bash
# 后端
cd stock-picker
PICKER_DB_DIR=/tmp/picker_db python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload

# 前端
cd stock-picker-vue
npm run dev
# → Vite 开发服务器, 默认 http://localhost:5173
# → API 代理到 http://127.0.0.1:8080/api
```

---

## 5. 配置与环境变量

### 5.1 config.py 核心配置

```python
# 数据库路径 (环境变量覆盖)
DATA_DIR  = $PICKER_DB_DIR or './data'
DB_PATH   = DATA_DIR + '/stocks.db'

# 腾讯财经 API
TENCENT_API = {
    'quote': 'http://qt.gtimg.cn/q=',
    'kline': 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get',
}

# 盘后调度
UPDATE_CONFIG = {
    'after_close': '20:00',    # K 线 + 行情 + RPS
    'daily_screen': '20:10',   # 选股缓存(在盘后之后)
}

# 4 策略默认阈值 (可被 DB 内 params_schema 覆盖)
STRATEGY_DEFAULTS = {
    'b1':   {'j_threshold': 18, ...},
    's2':   {'min_rps50': 85, ...},
    's3':   {'min_rps50': 90, 'min_rps120': 93, 'min_rps250': 95, 'near_high_threshold': 0.85},
    'kd1':  {'min_rps': 95, 'near_high_threshold': 0.6},
}

# RPS 周期
RPS_PERIODS = [50, 120, 250]
```

### 5.2 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `PICKER_DB_DIR` | 数据库文件夹(含 stocks.db) | `stock-picker/data/` |
| `PICKER_LOG_LEVEL` | 日志级别 | `INFO` |
| `VITE_API_PROXY` | 前端代理目标 | `http://127.0.0.1:8080/api` |

### 5.3 数据库 schema 迁移

**集中式**: SCHEMA_MIGRATIONS 字典,启动时幂等执行。加新列只需:
```python
SCHEMA_MIGRATIONS = {
    'template_screen_cache': {
        'existing_col': 'REAL',
        'new_col': 'INTEGER DEFAULT 0',  # 加这一行
    },
}
```
无需引入 alembic 依赖。

---

## 6. 公式引擎

### 6.1 语法

```
program   := (assign ';')* expr
assign    := ID ':=' expr
expr      := or_expr
or_expr   := and_expr (OR and_expr)*
and_expr  := not_expr (AND not_expr)*
not_expr  := NOT not_expr | cmp_expr
cmp_expr  := add_expr ((<=|>=|!=|=|<|>) add_expr)?
add_expr  := mul_expr (('+'|'-') mul_expr)*
mul_expr  := unary (('*'|'/') unary)*
unary     := '-' unary | primary
primary   := NUMBER | ID | ID '(' args ')' | '(' expr ')'
args      := expr (',' expr)*
```

### 6.2 内置函数

| 函数 | 参数 | 含义 | 实现 |
|------|------|------|------|
| `MA(X, N)` | 序列, 周期 | N 日简单移动平均 | `pd.Series.rolling(N).mean()` |
| `EMA(X, N)` | 序列, 周期 | N 日指数移动平均 | `pd.Series.ewm(span=N).mean()` |
| `REF(X, N)` | 序列, 步数 | N 日前值 | `s[N:] = s[:-N]` |
| `COUNT(X, N)` | 布尔序列, 周期 | 过去 N 日 X 为真的天数 | `rolling(N).sum()` |
| `HHV(X, N)` | 序列, 周期 | N 日最高值 | `rolling(N).max()` |
| `LLV(X, N)` | 序列, 周期 | N 日最低值 | `rolling(N).min()` |
| `CROSS(A, B)` | 序列, 序列 | A 上穿 B | `(A>B) & (prev_A <= prev_B)` |

### 6.3 字段别名

| 公式写法 | 实际字段 | 来源 |
|---------|---------|------|
| `CLOSE` | close | daily_df.close |
| `OPEN` | open | daily_df.open |
| `HIGH` | high | daily_df.high |
| `LOW` | low | daily_df.low |
| `VOL` | volume | daily_df.volume |
| `KDJ_K` | kdj_k | indicators._build_series |
| `KDJ_D` | kdj_d | indicators._build_series |
| `KDJ_J` | kdj_j | indicators._build_series |
| `RPS50/120/250` | rps50... | stock_rps 表(标量) |
| `PE_TTM` | pe_ttm | stock_quote_snapshot(标量) |
| `MA5...250` | ma5... | indicators._build_series |

### 6.4 内置模板公式

**b1 空谷幽兰**:
```
ZXDQ := EMA(EMA(CLOSE, 10), 10);
ZXDKX := (MA(CLOSE, 14) + MA(CLOSE, 28) + MA(CLOSE, 57) + MA(CLOSE, 114)) / 4;
KDJ_J < 18 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX
```

**s2 月线反转**:
```
CLOSE > MA(CLOSE, 250)
AND COUNT(HIGH >= HHV(HIGH, 50), 30) > 0
AND RPS50 >= 85
AND COUNT(CLOSE > MA(CLOSE, 250), 30) > 2
AND COUNT(CLOSE > MA(CLOSE, 250), 30) < 30
AND CLOSE / HHV(HIGH, 100) > 0.9
```

**s3 RPS三线红**:
```
RPS50 > 90 AND RPS120 > 93 AND RPS250 > 95 AND CLOSE / HHV(HIGH, 250) > 0.85
```

**kd1 一线红**:
```
(RPS50 > 95 OR RPS120 > 95 OR RPS250 > 95) AND CLOSE / HHV(HIGH, 250) > 0.6
```

### 6.5 用户自定义公式(示例)

```sql
-- 低估值 + 放量
PE_TTM < 15 AND PB < 2 AND VOL > MA(VOL, 20) * 1.5

-- 均线多头
MA5 > MA10 AND MA10 > MA20 AND CLOSE > MA5 AND RPS50 > 80

-- MACD 金叉
CROSS(MACD_DIF, MACD_DEA)
```

---

## 7. 缓存体系

### 7.1 三层缓存

```
请求到达
    ↓
[L1] 模板结果缓存 (template_screen_cache)
    ├── 盘后 4 策略跑完后落库
    ├── 前端 sidebar 数量 (template-summary) 走这里
    ├── 前端模板结果列表 (template-results) 走这里
    └── 按策略/日期分页,内置 ST 过滤/市场/行业/关键词
    ↓
[L2] K 线缓存 (stock_kline_cache)
    ├── 盘后对每只股票的日 K 重采样周/月
    ├── 一次性算好 MA5/20/60/120/250 + KDJ
    ├── stock_kline_cache 直接返回给前端,无需实时算
    └── 缺失时降级:
            get_daily_data_df() → resample → indicators 实时算 MA/KDJ → 返回
    ↓
[L3] RPS 预计算 (stock_rps)
    ├── 每日全量重建: pivot → pct_change → rank(pct) × 100
    ├── 策略 s2/s3/kd1 依赖 RPS
    └── _prefilter_for_strategy 用 RPS 缩小候选集
```

### 7.2 详情页 template_hits 快路径

```
请求 /api/stocks/{code}
    ↓
get_stock_detail(code)
    ↓
_build_template_hits(code, basic, daily_df, rps_df)
    ├── get_template_hits_for_code(code)  ← L1 缓存
    │   命中? → 直接返回 [
    │       {template_id, strategy_id, name, group_name, reason, matched},
    │       ...
    │   ]
    └── 未命中? → 降级实时算 4 策略 (慢)
```

### 7.3 缓存刷新

| 操作 | 命令 | 频率 |
|------|------|------|
| RPS 重建 | `--rps-only` | 每日盘后 |
| 模板缓存重建 | `--cache-only` | 每日盘后 |
| K 线缓存重建 | `build_kline_cache_batch()` | 手动/每日盘后 |
| 全量刷新 | `--daily-update` | 每日 20:00 |

---

## 8. API 文档

### 8.1 接口总览

| 方法 | 路径 | 用途 | OpenAPI tag |
|------|------|------|-------------|
| GET | `/api/health` | 健康检查 | health |
| GET | `/api/health/live` | K8s liveness | health |
| GET | `/api/health/ready` | K8s readiness(检查 DB + 缓存) | health |
| GET | `/api/formula/templates` | 内置模板列表 | templates |
| GET | `/api/formula/templates/{id}` | 单个模板详情 | templates |
| POST | `/api/formula/validate` | 公式校验 | templates |
| POST | `/api/stocks/search` | 股票搜索(基础筛选+公式+模板) | search |
| POST | `/api/stocks/template-results` | 模板预计算缓存结果 | search |
| GET | `/api/stocks/template-summary` | 模板命中摘要(数量) | search |
| GET | `/api/stocks/{code}` | 股票详情(行情+技术+财务+K线+命中) | detail |
| GET | `/api/kline/{code}` | K 线(日/周/月,带 MA+KDJ) | detail |
| GET | `/api/strategies` | 策略列表 | search |
| POST | `/api/screen` | 选股(4 策略并行) | (legacy) |

### 8.2 关键请求/响应

#### POST /api/formula/validate
```json
// 请求
{"formula": "RPS50 > 90 AND CLOSE / HHV(HIGH, 250) > 0.85"}

// 响应
{
  "valid": true,
  "errors": [],
  "used_fields": ["close", "high", "rps50"],
  "normalized_formula": "RPS50 > 90 AND CLOSE / HHV(HIGH, 250) > 0.85"
}
```

#### POST /api/stocks/search
```json
// 请求 (基础筛选 + 公式)
{
  "markets": ["SZA"],
  "industries": ["银行", "食品饮料"],
  "keyword": "茅台",
  "filters": {
    "include_st": false,
    "exclude_suspended": true,
    "min_total_mv": 100_000_000_000
  },
  "formula": "RPS50 > 85 AND MA5 > MA20",
  "formula_text": "",
  "sort_by": "rps50",
  "sort_order": "desc",
  "page": 1,
  "page_size": 20
}

// 响应
{
  "items": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "market": "SHA",
      "industry": "食品饮料",
      "price": 1750.0,
      "change_pct": 2.35,
      "total_mv": 2.1e12,
      "rps50": 92.5,
      "rps120": 88.3,
      "rps250": 95.1,
      "reason": "基础筛选命中",
      ...
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "applied_formula": "RPS50 > 85 AND MA5 > MA20"
}
```

#### GET /api/stocks/{code}
```json
{
  "basic": {"code": "600519", "name": "贵州茅台", "market": "SHA", "industry": "食品饮料", "listed_date": "2001-08-27"},
  "quote": {"trade_date": "2026-06-17", "price": 1750.0, "change_pct": 2.35, "volume": 5800000, "total_mv": 2.1e12},
  "fundamentals": {"pe_ttm": 28.5, "pb": 8.2, "roe_ttm": 32.1},
  "technicals": {
    "ma5": 1720.0, "ma20": 1680.0, "ma60": 1620.0,
    "rsi14": 58.3, "macd_dif": 12.5, "macd_hist": 3.2,
    "kdj_k": 65.3, "kdj_d": 58.1, "kdj_j": 79.7,
    "rps50": 92.5, "rps120": 88.3, "rps250": 95.1
  },
  "kline_summary": {"last_trade_date": "2026-06-17", "day_count": 6230, "highest_250d": 1780},
  "template_hits": [
    {"template_id": 1, "strategy_id": "b1", "name": "空谷幽兰", "matched": false},
    {"template_id": 2, "strategy_id": "s2", "name": "月线反转", "matched": false},
    {"template_id": 3, "strategy_id": "s3", "name": "RPS三线红", "matched": true},
    {"template_id": 4, "strategy_id": "kd1", "name": "一线红", "matched": false}
  ]
}
```

#### GET /api/kline/{code}?period=day
```json
{
  "code": "600519",
  "period": "day",
  "data": [
    {"date": "2026-06-12", "open": 1725, "high": 1748, "low": 1720, "close": 1745, "volume": 6100000}
  ],
  "ma5": [1710, 1712, ...],
  "ma20": [1695, 1698, ...],
  "ma60": [1660, 1662, ...],
  "k": [60.5, 61.2, ...],
  "d": [55.3, 56.0, ...],
  "j": [70.9, 71.6, ...],
  "rps": {"rps50": 92.5, "rps120": 88.3, "rps250": 95.1}
}
```

---

## 9. 前端交互

### 9.1 页面加载流程

```
1. App.vue onMounted()
    → store.boot()
      ├── api.templates()          → /api/formula/templates
      ├── api.templateSummary()    → /api/stocks/template-summary
      └── 选中第 3 个模板 (s3)
          └── api.templateResults() → /api/stocks/template-results {template_id:3}
              (多页自动全拉, page_size=5000, 一次性拿完)

2. 自动选中第一只股票
    → api.stockDetail(code)   → /api/stocks/{code}
    → api.kline(code, 'day')  → /api/kline/{code}?period=day

3. 用户点击左侧模板
    → store.selectTemplate(id)
      → api.templateResults({template_id:id})

4. 用户点击股票行
    → store.loadDetail(code)
      → api.stockDetail(code) + api.kline(code, period)

5. 日/周/月按钮
    → selectedPeriod 变量变化
    → KlineChart watch → api.kline(code, period)

6. Mock 兜底 (后备方案)
    → 所有 API 请求失败时自动 fallback 到 mock.js
    → 前端模板/结果/详情全有离线示例数据
```

### 9.2 前端状态管理(Pinia store)

```javascript
state: {
  templates,        // 4 个模板定义 (从 /api/formula/templates)
  summaries,        // 各模板命中数量 (从 /api/stocks/template-summary)
  activeTemplateId,  // 当前选中模板ID
  items,            // 当前筛选结果列表
  total,            // 命中总数
  date,             // 最新交易日
  selectedCode,     // 当前选中股票代码
  detail,           // 详情缓存 Map
  cacheHit,         // 是否命中盘后缓存
}
```

---

## 10. 调度与维护

### 10.1 APScheduler 定时任务

在 uvicorn 进程内通过 `scheduler.start_scheduler()` 启动:

```
20:00 → run_after_close_update()
    │    ├── sync_stock_basic()              # 同步股票池
    │    ├── batch_update_daily_data()       # 增量拉今天日线
    │    └── _rebuild_rps_and_cache()        # RPS + 模板缓存

20:10 → run_daily_screen()
         ├── engine.screen([b1,s2,s3,kd1])  # 跑 4 个策略
         └── save_template_screen_results()  # 落缓存
```

### 10.2 手动刷新命令

```bash
# 只看 RPS
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --rps-only

# 只看模板缓存
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --cache-only

# 完整盘后更新
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --daily-update

# 重建 K 线缓存
PICKER_DB_DIR=/tmp/picker_db python3 -c "
from data.store import build_kline_cache_batch, get_stocks
codes = get_stocks()['code'].astype(str).tolist()
build_kline_cache_batch(codes)
"
```

### 10.3 日志

```
格式: [YYYY-MM-DD HH:MM:SS] LEVEL   module: message
示例: [2026-06-18 20:00:05] INFO    engine.screening: 扫描 5128 只股票...
       [2026-06-18 20:00:06] WARNING strategies.b1_strategy: b1 评估 000003 失败: ...
       [2026-06-18 20:00:10] INFO    scripts_refresh_latest: RPS 重建完成: 3800 只
```

`PICKER_LOG_LEVEL=DEBUG` 可看到更多细节。

### 10.4 数据库维护

```bash
# 查看各表行数
sqlite3 $PICKER_DB_DIR/stocks.db "SELECT name, COUNT(*) FROM (SELECT 'stock_basic' name UNION ALL SELECT 'stock_daily' ...) ..."

# 备份
cp $PICKER_DB_DIR/stocks.db $PICKER_DB_DIR/stocks_$(date +%Y%m%d).bak

# 优化 (重建索引)
sqlite3 $PICKER_DB_DIR/stocks.db "VACUUM; ANALYZE;"
```

---

## 11. 性能指标

### 11.1 基准测试结果(50 只样本)

| 指标 | 目标 | 实际 | 余量 |
|------|------|------|------|
| POST /api/stocks/search (空搜索) | < 2000ms | **100ms** | 20× |
| GET /api/stocks/{code} (详情页) | < 1000ms | **43ms** | 23× |
| GET /api/kline/{code} (日 K) | < 1000ms | **37ms** | 27× |
| GET /api/kline/{code} (周 K) | < 1000ms | **28ms** | 36× |
| GET /api/kline/{code} (月 K) | < 1000ms | **34ms** | 29× |
| POST /api/stocks/template-results | < 1000ms | **0.1ms** | 10000× |
| evaluate_formula (单只) | < 100ms | **2ms** | 50× |

### 11.2 性能关键设计

1. **策略向量化**: 5000 只股票 1 次 groupby + rolling/ewm,不逐股 for
2. **模板缓存**: 盘后全跑一遍存 template_screen_cache,线上只读
3. **K 线缓存**: stock_kline_cache 日/周/月 + MA/KDJ 一次算好,详情页直接读
4. **RPS 预筛选**: engine._prefilter_for_strategy 用 RPS 缩小候选集(比如 s3 只扫 RPS50>85 的股)
5. **详情页快路径**: template_hits 从 template_hits_json 直接读,不用现算
6. **SQLite WAL 模式**: 读不阻塞写(盘后更新和 API 查询可以并发)

### 11.3 可扩展点

- **全量 5500 只**: 确认指标; 瓶颈在 RPS 的 pivot 矩阵 (5500×600),约需 10-15 秒(每日一次,可接受)
- **PostgreSQL 迁移**: 改 `get_conn` 指向 PG 即可,SQL 层抽象好了
- **Redis 缓存**: K 线/详情页的热点可由 Redis 前置,进一步降延迟
- **多进程**: FastAPI workers 设置多个进程(每个有独立 SQLite 连接),读负载可以扩展

---

## 附录 A: 所有文件清单

```
stock-system/
├── REQUIREMENTS.md                 — 一期需求 (已冻结)
├── RUN.md                          — 本地运行指南
├── to_do_list.md                   — 改造进度追踪 (P0/P1/P2 全部完成)
├── hsjday 2/                       — 通达信日线数据
├── data/tencent_hs.json            — 全 A 股票池
├── stock-picker/                   — Python 后端
│   ├── app.py                      — FastAPI 入口 (lifespan + OpenAPI)
│   ├── engine.py                   — mixin 拼装入口 (26 行)
│   ├── engine/
│   │   ├── base.py                 — 工具方法 + ScreeningEngine 主类
│   │   ├── screening.py            — 选股 + build_template_result_snapshot
│   │   ├── search.py               — 搜索 + 公式引擎实时求值
│   │   ├── detail.py               — 详情页组装
│   │   ├── kline.py                — K 线(缓存优先 + 降级实时)
│   │   └── cache.py                — 模板缓存读
│   ├── formula_engine.py           — 类通达信公式解析/求值/校验
│   ├── indicators.py               — 向量化指标 (MA/EMA/MACD/RSI/KDJ/HHV)
│   ├── strategies/
│   │   ├── base.py / __init__.py   — 策略基类 + 注册表
│   │   ├── b1_strategy.py          — 空谷幽兰
│   │   ├── s2_strategy.py          — 月线反转
│   │   ├── s3_strategy.py          — RPS三线红
│   │   └── kd1_strategy.py         — 一线红
│   ├── data/
│   │   ├── store.py                — SQLite 数据层 (8 表 + SCHEMA_MIGRATIONS)
│   │   └── fetcher.py              — 腾讯行情 + K 线 + 并发更新
│   ├── api/
│   │   ├── routes.py               — 9 个路由
│   │   └── schemas.py              — Pydantic 模型 + OpenAPI tags
│   ├── logger.py                   — 统一日志
│   ├── scheduler.py                — APScheduler 定时任务
│   ├── scripts_refresh_latest.py   — 盘后更新工具
│   ├── scripts/
│   │   ├── bench.py                — 性能回归测试
│   │   └── import_hsjday_to_sqlite.py — .day 文件导入
│   ├── tests/                      — 70 个 pytest,100% 通过
│   │   ├── conftest.py             — 临时 DB fixture
│   │   ├── test_formula_engine.py  — 公式引擎单测
│   │   ├── test_indicators.py      — 指标单测
│   │   ├── test_store.py           — 数据层单测
│   │   └── test_api.py             — API 集成测试
│   ├── requirements.txt            — 依赖
│   └── pytest.ini                  — pytest 配置
├── stock-picker-vue/               — Vue 3 前端
│   ├── src/
│   │   ├── App.vue                 — 主布局
│   │   ├── stores/picker.js        — Pinia store
│   │   ├── lib/api.js              — API 客户端
│   │   ├── data/mock.js            — 离线 mock 数据
│   │   └── components/
│   │       ├── KlineChart.vue       — K 线图表 (lightweight-charts)
│   │       ├── StockDetailPanel.vue — 详情面板
│   │       ├── StrategySidebar.vue  — 侧边栏
│   │       └── StockBoard.vue       — 股票列表
│   ├── package.json / vite.config.js / tailwind.config.cjs
│   └── README.md
└── scripts/                        — 已 DEPRECATED 的工具脚本
    └── (空壳桩子)
```
