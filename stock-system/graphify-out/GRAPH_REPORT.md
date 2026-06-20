# Graph Report - .  (2026-06-20)

## Corpus Check
- 86 files · ~105,504 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 619 nodes · 1308 edges · 55 communities (38 shown, 17 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 222 edges (avg confidence: 0.6)
- Token cost: 0 input · 235,196 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Formula Engine|Formula Engine]]
- [[_COMMUNITY_API Routes|API Routes]]
- [[_COMMUNITY_Technical Indicators|Technical Indicators]]
- [[_COMMUNITY_Engine Cache Layer|Engine Cache Layer]]
- [[_COMMUNITY_Data Fetching|Data Fetching]]
- [[_COMMUNITY_API Tests|API Tests]]
- [[_COMMUNITY_Data Store Tests|Data Store Tests]]
- [[_COMMUNITY_Data Store Core|Data Store Core]]
- [[_COMMUNITY_Workflow Documentation|Workflow Documentation]]
- [[_COMMUNITY_Vue Dependencies|Vue Dependencies]]
- [[_COMMUNITY_Screening Engine|Screening Engine]]
- [[_COMMUNITY_Vue App Component|Vue App Component]]
- [[_COMMUNITY_Data Refresh Pipeline|Data Refresh Pipeline]]
- [[_COMMUNITY_Data Store Utilities|Data Store Utilities]]
- [[_COMMUNITY_Stock Detail Engine|Stock Detail Engine]]
- [[_COMMUNITY_UI Design Preview|UI Design Preview]]
- [[_COMMUNITY_Scheduler & Strategies|Scheduler & Strategies]]
- [[_COMMUNITY_RPS & Quote Data|RPS & Quote Data]]
- [[_COMMUNITY_FastAPI App Bootstrap|FastAPI App Bootstrap]]
- [[_COMMUNITY_Base Strategy Abstract|Base Strategy Abstract]]
- [[_COMMUNITY_Concrete Strategies|Concrete Strategies]]
- [[_COMMUNITY_Vue State & Mock|Vue State & Mock]]
- [[_COMMUNITY_HS Day Import Script|HS Day Import Script]]
- [[_COMMUNITY_Kline Cache Engine|Kline Cache Engine]]
- [[_COMMUNITY_DB Health & Readiness|DB Health & Readiness]]
- [[_COMMUNITY_Benchmarks & Migration|Benchmarks & Migration]]
- [[_COMMUNITY_Template Screening|Template Screening]]
- [[_COMMUNITY_Vue Stock Detail Panel|Vue Stock Detail Panel]]
- [[_COMMUNITY_KD1 Strategy|KD1 Strategy]]
- [[_COMMUNITY_S2 Strategy|S2 Strategy]]
- [[_COMMUNITY_Test Conftest|Test Conftest]]
- [[_COMMUNITY_Test Init|Test Init]]
- [[_COMMUNITY_Docker Watchdog|Docker Watchdog]]
- [[_COMMUNITY_Bench Script|Bench Script]]
- [[_COMMUNITY_Parquet Conversion|Parquet Conversion]]
- [[_COMMUNITY_Pack HS Script|Pack HS Script]]
- [[_COMMUNITY_Tencent Crosscheck|Tencent Crosscheck]]
- [[_COMMUNITY_Simple Server|Simple Server]]
- [[_COMMUNITY_Docker Entrypoint|Docker Entrypoint]]
- [[_COMMUNITY_Stock Data JS|Stock Data JS]]
- [[_COMMUNITY_Engine Package Init|Engine Package Init]]
- [[_COMMUNITY_After-Close Scheduler|After-Close Scheduler]]
- [[_COMMUNITY_Requirements Dependencies|Requirements Dependencies]]
- [[_COMMUNITY_Vue README|Vue README]]
- [[_COMMUNITY_Claude Graphify Section|Claude Graphify Section]]
- [[_COMMUNITY_TODO Optimization List|TODO Optimization List]]

## God Nodes (most connected - your core abstractions)
1. `get_cursor()` - 38 edges
2. `FormulaError` - 30 edges
3. `StockSearchRequest` - 28 edges
4. `FormulaCreate` - 27 edges
5. `FormulaUpdate` - 27 edges
6. `FormulaValidateRequest` - 27 edges
7. `ScreenRequest` - 27 edges
8. `Node` - 23 edges
9. `evaluate_formula()` - 23 edges
10. `Parser` - 16 edges

## Surprising Connections (you probably didn't know these)
- `load_tencent_hs_list()` --calls--> `Path`  [INFERRED]
  stock-picker/data/fetcher.py → scripts/import_hsjday_to_sqlite.py
- `REST API Design (6 endpoint groups)` --conceptually_related_to--> `ScreeningEngine (Mixin modules)`  [INFERRED]
  REQUIREMENTS.md → stock-picker/WORKFLOW.md
- `Stock Data Models (7 tables)` --conceptually_related_to--> `SQLite Data Store (8 tables)`  [INFERRED]
  REQUIREMENTS.md → stock-picker/WORKFLOW.md
- `Docker Compose Deployment` --conceptually_related_to--> `ScreeningEngine (Mixin modules)`  [INFERRED]
  docker-compose.yml → stock-picker/WORKFLOW.md
- `get_strategies()` --calls--> `list_strategies()`  [INFERRED]
  stock-picker/api/routes.py → stock-picker/strategies/__init__.py

## Import Cycles
- 1-file cycle: `stock-picker/app.py -> stock-picker/app.py`
- 2-file cycle: `stock-picker/api/routes.py -> stock-picker/app.py -> stock-picker/api/routes.py`

## Hyperedges (group relationships)
- **Four Built-in Stock Screening Strategies** — stock_system_requirements_strategy_templates, stock_picker_workflow_builtin_strategies, stock_system_requirements_rps_system [EXTRACTED 1.00]
- **Backend Engine Architecture** — stock_picker_workflow_screening_engine, stock_picker_workflow_formula_engine_parser, stock_picker_workflow_indicators, stock_picker_workflow_data_store, stock_picker_workflow_data_fetcher, stock_picker_workflow_cache_system [EXTRACTED 1.00]
- **AAPL Stock Detail View Components** — stock_system_apple_stock_detail_header, stock_system_apple_stock_price_chart, stock_system_kline_candlestick_chart, stock_system_apple_financial_metrics, stock_system_apple_technical_indicators, stock_system_apple_company_overview, stock_system_stock_score_rating [INFERRED 0.85]
- **Stock Screening and Results Workflow** — stock_system_formula_screening_interface, stock_system_stock_ranking_table, stock_system_stock_score_rating, stock_system_portfolio_summary_section [INFERRED 0.85]

## Communities (55 total, 17 thin omitted)

### Community 0 - "Formula Engine"
Cohesion: 0.07
Nodes (39): Any, BinOp, _build_series(), _compare(), _count(), _cross(), evaluate_formula(), Evaluator (+31 more)

### Community 1 - "API Routes"
Cohesion: 0.14
Nodes (56): add_formula(), get_formula(), get_formula_template(), get_quotes(), get_stock_detail(), get_strategies(), get_template_results(), get_template_summary() (+48 more)

### Community 2 - "Technical Indicators"
Cohesion: 0.10
Nodes (25): compute_all(), compute_ema(), compute_hhv(), compute_kdj(), compute_ma(), compute_macd(), compute_rsi(), _ensure_sorted() (+17 more)

### Community 3 - "Engine Cache Layer"
Cohesion: 0.11
Nodes (15): _Base, CacheMixin, CacheMixin: 模板预计算缓存读。, 提供 `get_cached_template_results()`。, engine 子包,提供选股引擎的核心类。  模块拆分:   - base       ScreeningEngine 主类、通用工具方法   - screen, 组合后的最终 ScreeningEngine(给 routes.py 用)。, ScreeningEngine, ScreeningMixin: 选股主流程 + 策略引擎调度。 (+7 more)

### Community 4 - "Data Fetching"
Cohesion: 0.13
Nodes (24): batch_update_daily_data(), _clear_daily_update_state(), _fingerprint_codes(), get_kline(), get_quote(), _get_session(), _infer_market(), _is_excluded_security() (+16 more)

### Community 5 - "API Tests"
Cohesion: 0.08
Nodes (9): API 集成测试: 用 TestClient 跑 5 个端点 + 公式校验。, TestFormulaTemplates, TestFormulaValidate, TestHealth, TestKLine, TestOpenAPI, TestSearch, TestStockDetail (+1 more)

### Community 6 - "Data Store Tests"
Cohesion: 0.08
Nodes (9): data.store 单元测试: 初始化 / 写入 / 读取 / schema migration / stocks 表迁移。, P1-7: 旧 stocks 表应被迁移后 DROP。, TestDailyData, TestInitDB, TestQuoteSnapshot, TestRPS, TestSchemaMigrations, TestStockBasic (+1 more)

### Community 7 - "Data Store Core"
Cohesion: 0.16
Nodes (21): create_formula(), delete_formula(), get_codes_needing_daily_update(), get_cursor(), get_formula_template_by_id(), get_formulas(), get_latest_daily_codes(), get_latest_daily_date_by_code() (+13 more)

### Community 8 - "Workflow Documentation"
Cohesion: 0.15
Nodes (21): After-Close Update Pipeline (APScheduler), Backend Architecture (Mixin Pattern), Four Built-in Strategies (B1/S2/S3/KD1), Three-Layer Cache System, Data Fetcher (Tencent/TDX sources), SQLite Data Store (8 tables), Formula Engine Recursive Descent Parser, Vectorized Indicators Engine (+13 more)

### Community 9 - "Vue Dependencies"
Cohesion: 0.11
Nodes (18): dependencies, lightweight-charts, pinia, vue, devDependencies, autoprefixer, postcss, tailwindcss (+10 more)

### Community 10 - "Screening Engine"
Cohesion: 0.20
Nodes (4): ScreeningEngine 主类、通用工具方法(_safe_float / _format_date 等)。, ScreeningEngine, Any, ndarray

### Community 11 - "Vue App Component"
Cohesion: 0.12
Nodes (12): activeSummary, displayDate, displayWeekday, handleGlobalKeydown(), headerDateLabel, isEditableTarget(), klineChange, klineChangeClass (+4 more)

### Community 12 - "Data Refresh Pipeline"
Cohesion: 0.18
Nodes (16): build_kline_cache_batch(), get_daily_data_df(), get_stocks(), 盘后批量建 K 线缓存: 对每只股票读 stock_daily,重采样,算 MA + KDJ,落 stock_kline_cache。, 获取所有股票(仅 stock_basic)。, save_quote_snapshots(), DataFrame, One-off refresh helpers for kline/RPS/template cache. (+8 more)

### Community 13 - "Data Store Utilities"
Cohesion: 0.25
Nodes (14): _coerce_flag(), get_stock_basic_by_code(), get_template_hits_for_code(), get_template_screen_result_page(), get_template_screen_results(), _normalize_concept_tags(), _normalize_stock_code(), 从 template_screen_cache 读单只股票的 template_hits_json(盘后预计算结果)。      返回 list[dict],每 (+6 more)

### Community 14 - "Stock Detail Engine"
Cohesion: 0.27
Nodes (7): DetailMixin, DetailMixin: 股票详情页组装。, 提供 `get_stock_detail()`。, 读取当前股票的 template_hits。          优先从 template_screen_cache.template_hits_json 读盘后, Series, Any, DataFrame

### Community 15 - "UI Design Preview"
Cohesion: 0.21
Nodes (15): App Navigation Bar with Tabs, Apple Company Overview Section, Apple Financial Metrics Display, AAPL Stock Detail Header with Price Data, Apple Stock Picker Preview, AAPL Price Chart Visualization, Apple Stock Technical Indicators Panel, Formula-Based Stock Screening Interface (+7 more)

### Community 16 - "Scheduler & Strategies"
Cohesion: 0.26
Nodes (7): Logger, 定时任务 - 每日收盘后自动执行选股与数据更新, b1 策略: KDJ_J < 阈值 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX (空谷幽兰)  向量化实现: 一次性把 daily_da, list_strategies(), kd1 策略: 一线红    (RPS50 > min_rps OR RPS120 > min_rps OR RPS250 > min_rps)   AND C, s2 策略: 月线反转    CLOSE > MA(CLOSE, 250)   AND COUNT(HIGH >= HHV(HIGH, 50), 30) > 0, s3 策略: RPS三线红    RPS50 > min_rps50   AND RPS120 > min_rps120   AND RPS250 > min_

### Community 17 - "RPS & Quote Data"
Cohesion: 0.23
Nodes (11): get_daily_data(), get_kline_cache(), get_latest_quote_snapshot(), get_rps_data(), get_rps_history(), get_stocks_by_codes(), _normalize_code_list(), 从 stock_kline_cache 读取预计算 K 线(快路径),返回可以直接返回给前端的 dict。 (+3 more)

### Community 18 - "FastAPI App Bootstrap"
Cohesion: 0.18
Nodes (10): FastAPI, api_entry(), lifespan(), Smart Stock Picker - FastAPI 主入口, 前端入口，保持浏览器中的 /api 地址可直接打开页面。, get_logger(), 统一日志配置。  调用 `setup_logging()` 一次即可。后续模块用 `logger = logging.getLogger(__name__)`。, 获取 logger(自动 setup_logging)。 (+2 more)

### Community 19 - "Base Strategy Abstract"
Cohesion: 0.18
Nodes (5): ABC, Any, BaseStrategy, 初始化策略         params: 可配置的参数，如 {'min_rps50': 90}, 执行选股         market_data 包含:         - stock_list: DataFrame 股票列表         - dail

### Community 20 - "Concrete Strategies"
Cohesion: 0.18
Nodes (5): BaseStrategy, BaseStrategy, B1Strategy, get_strategy(), S3Strategy

### Community 21 - "Vue State & Mock"
Cohesion: 0.29
Nodes (5): mockDetail, mockStocks, mockTemplates, api, usePickerStore

### Community 22 - "HS Day Import Script"
Cohesion: 0.36
Nodes (9): Path, get_conn(), import_one_code(), load_existing_codes(), locate_day_file(), main(), parse_day_file(), Connection (+1 more)

### Community 23 - "Kline Cache Engine"
Cohesion: 0.28
Nodes (5): _build_cache_rows_for_code(), 为单只股票计算各周期的 K 线 + MA + KDJ，返回可 executemany 的 tuple 列表。, KLineMixin, KLineMixin: K 线 + 周月重采样。  优先从 stock_kline_cache 读盘后预计算结果,无缓存时才从 stock_daily 实时算。, 提供 `get_kline()`,支持日/周/月,优先走缓存。

### Community 24 - "DB Health & Readiness"
Cohesion: 0.25
Nodes (8): health_ready(), K8s readiness probe: DB 连得通 + stock_basic 有数据 + 今日模板缓存有数据。, get_conn(), get_latest_date(), get_template_screen_summary(), 获取内置模板最新缓存摘要，供左侧数量展示使用。, 获取数据库连接(单例长连接 + WAL)。, Connection

### Community 25 - "Benchmarks & Migration"
Cohesion: 0.29
Nodes (7): _apply_pending_migrations(), init_db(), 对 SCHEMA_MIGRATIONS 中声明的列做幂等 ALTER。, 跑 fn repeat 次,返回 (中位数毫秒, 每次毫秒列表)。, time_it(), main(), 性能回归测试 bench.py。  衡量三项关键指标(对齐 REQUIREMENTS.md 9.1):   - 单次 /api/stocks/template-

### Community 26 - "Template Screening"
Cohesion: 0.40
Nodes (6): get_formula_templates(), 保存内置模板预计算结果。      results 可以是只含 code/name 的策略命中结果，也可以是已经富化好的     前端列表快照。富化字段会一起落, save_template_screen_results(), run_daily_screen(), 仅基于本地 stock_daily / stock_rps 重新生成模板缓存。, rebuild_template_cache_from_local_data()

### Community 30 - "Test Conftest"
Cohesion: 0.50
Nodes (3): _isolated_db(), 测试 fixtures 共享。  每个测试用临时 sqlite DB + 清空 store._CONN,确保隔离。, 每个测试用一个临时 sqlite 文件,且强制重置单例连接。

### Community 31 - "Test Init"
Cohesion: 0.50
Nodes (3): _isolated_db(), 测试 fixtures 共享。  约定: 每个测试用临时 sqlite DB + 清空 store._CONN,确保隔离。, 每个测试用一个临时 sqlite 文件,且强制重置单例连接。

## Knowledge Gaps
- **42 isolated node(s):** `entrypoint.sh script`, `STOCK_DATA`, `name`, `private`, `version` (+37 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FormulaError` connect `Formula Engine` to `API Routes`, `Technical Indicators`, `Engine Cache Layer`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `evaluate_formula()` connect `Formula Engine` to `RPS & Quote Data`, `Engine Cache Layer`, `Benchmarks & Migration`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `Logger` connect `Scheduler & Strategies` to `FastAPI App Bootstrap`, `Engine Cache Layer`, `Data Refresh Pipeline`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `FormulaError` (e.g. with `ScreeningMixin` and `SearchMixin`) actually correct?**
  _`FormulaError` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `StockSearchRequest` (e.g. with `FormulaCreate` and `FormulaResponse`) actually correct?**
  _`StockSearchRequest` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `FormulaCreate` (e.g. with `FormulaCreate` and `FormulaResponse`) actually correct?**
  _`FormulaCreate` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `FormulaUpdate` (e.g. with `FormulaCreate` and `FormulaResponse`) actually correct?**
  _`FormulaUpdate` has 26 INFERRED edges - model-reasoned connections that need verification._