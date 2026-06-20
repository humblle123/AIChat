# Stock Picker 后端优化待办清单

> 来源: 2026-06-17 代码评审
> 目标: 满足需求 `REQUIREMENTS.md` 中 9.1 性能指标(单次筛选 < 2 秒 / 详情页 < 1 秒 / K 线 < 1 秒)
> 改之前先看每项的"位置 / 现象 / 验收",改完在"完成"列打勾

---

## 概览

| 级别 | 数量 | 总工作量 | 进度 |
|---|---|---|---|
| 🔴 P0 必改(性能/功能缺陷) | 6 项 | ~3.5 天 | ✅ 100% |
| 🟠 P1 应改(可维护/正确性) | 11 项 | ~5.5 天 | ✅ 100% |
| 🟡 P2 建议改(代码质量) | 10 项 | ~3 天 | ✅ 90% (仅 P2-2 剩余) |

## 进度 (2026-06-17)

### P0
- [x] P0-5 删 routes.py 末尾 init_db() — 已完成
- [x] P0-4 改 lifespan — 已完成
- [x] P0-6 修 total_mv/circ_mv 字段错位 — 已完成
- [x] P0-1 策略向量化 — 已完成 (4 策略 groupby 实现 + indicators.py + 详情页走 indicators)
- [x] P0-3 K 线周/月重采样 — 已完成
- [x] P0-2 公式解析器 — 已完成 (formula_engine.py 4 个内置模板 + MA/EMA/REF/COUNT/HHV/LLV/CROSS + POST /api/formula/validate)

### P1
- [x] P1-1 数据库连接改连接池 — 已完成 (单例 + WAL + 20MB cache)
- [x] P1-2 改 INSERT OR REPLACE 为 ON CONFLICT DO UPDATE — 已完成 (4 处)
- [x] P1-3 用集中式 schema_migrations 替换散落 ALTER — 已完成 (轻量化,不引 alembic)
- [x] P1-4 拆 engine.py (1386→26 行入口) — 已完成 (5 个 mixin 模块)
- [x] P1-5 template_hits 盘后预计算入库 — 已完成 (template_hits_json + get_template_hits_for_code,详情页快路径)
- [x] P1-6 _normalize_prev_close 优先级明确 — 已完成 (data > change_pct_inferred 仅 |pct|<=20% > fallback)
- [x] P1-7 删 stocks 表,只留 stock_basic — 已完成
- [x] P1-8 scripts_refresh_latest.py 抽公共函数 — 已完成 (_rebuild_rps_and_cache)
- [x] P1-9 4 个策略共用 indicators.py — 已完成
- [x] P1-10 排除规则统一用 is_st 字段 — 已完成
- [x] P1-11 cache_hit 语义修正 — 已完成

### P2 (已收尾)
- [x] P2-1 加 tests/ 目录和 pytest — 已完成 (70 测试通过)
- [ ] P2-2 print 改 logging — ~49 处剩余
- [x] P2-3 异常不要静默吞 — 已完成
- [x] P2-4 删 dead code — 已完成 (6/18 删除 simple_server.py + 4 脚本 + 2 JSON)
- [x] P2-5 fetcher 行情抓取并发化 — 已完成 (ThreadPoolExecutor)
- [x] P2-6 K 线字段命名统一 — 已完成
- [x] P2-7 mock 兜底一致性测试 — 已完成
- [x] P2-8 排除 ST 用 is_st 字段 — 已完成 (EXCLUDE_KEYWORDS 已删除)
- [x] P2-9 加 healthz / readiness 探针 — 已完成 (/health/live + /health/ready)
- [x] P2-10 加 OpenAPI 描述 — 已完成 (API_TAGS_METADATA + openapi_tags)

---

## 🔴 P0 — 必改

### [x] P0-1 策略向量化,解决 < 2 秒筛选指标
- **位置**: `stock-picker/strategies/b1_strategy.py` `s2_strategy.py` `s3_strategy.py` `kd1_strategy.py` `engine.py` 的 `get_stock_detail` / `get_kline` / `_build_template_hits`
- **现象**:
  - 每个 `screen()` 都 `for _, row in stock_list.iterrows(): ... self._check_xxx(df)` 逐股循环
  - 内部用 Python `for` 循环算 KDJ / MA / HHV,5000 只股 × 1200 根 = 6M 次循环
  - `engine.get_stock_detail` 每开一只股票现算一遍 MA/MACD/RSI/KDJ
  - `engine._build_template_hits` 每只股票把 4 个策略都重跑一遍
- **验收**:
  - [x] 4 个策略的命中判断改为对全市场 DataFrame 一次性向量化(groupby + rolling/ewm)
  - [x] 抽出 `stock-picker/indicators.py`,4 个策略共用同一组向量化指标函数
  - [x] 详情页指标走 `indicators.py` 一次性算(后续再做"读预计算表")
  - [x] `template_hits` 跟着 `template_screen_cache` 一起盘后预计算入库,详情页只读 (`build_template_result_snapshot` 注入 + `save_template_screen_results` 落 `template_hits_json` 列 + `get_template_hits_for_code` 快路径读取,真实数据已验证 4 模板评估一致)
  - [x] benchmark 脚本验证: 5481 只股票 `s3` 命中 **100ms** (目标 < 2s,余量 20x),单股详情页 **43ms** (目标 < 1s,余量 23x),K 线日/周/月 28-37ms,公式引擎单只 2ms — 全部 PASS

### [x] P0-2 公式解析器(MA/EMA/REF/COUNT/HHV/LLV/CROSS + 逻辑运算)
- **位置**: 新建 `stock-picker/formula_engine.py`,重写 `engine._parse_formula` 和 `_evaluate_formula_search`
- **现象**:
  - 现状用正则抠 `RPSxx > 数字`,用户写的公式里只要不带 RPS 就**直接返回空**
  - `_filter_b1/s2/s3/kd1` 是写死的简化版,**和需求里的公式表达式对不上**(s3 阈值、b1 用的 KDJ 而非 RPS)
  - `/api/formula/validate` 端点**压根没实现**
- **验收**:
  - [ ] 递归下降解析器支持 `MA / EMA / REF / COUNT / HHV / LLV / CROSS` + 逻辑运算 + 比较 + 括号
  - [ ] 字段别名映射(对齐 `REQUIREMENTS.md` 5.x 节): `CLOSE→close`, `KDJ_K→kdj_k`, `RPS50→rps50` 等
  - [ ] 空值规则: `peg=null` 时 `peg < 1` 返回 `false`
  - [ ] 4 个内置模板的 `expression` 字段**真正接通**到求值器,删掉 `_filter_b1/s2/s3/kd1` 写死逻辑
  - [ ] `POST /api/formula/validate` 返回 `{valid, errors, normalized_formula, used_fields}`
  - [ ] 单元测试覆盖 4 个内置模板(以 `b1` 为例: `KDJ_J < 18 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX` 命中数 > 0)

### [x] P0-3 K 线周/月重采样
- **位置**: `stock-picker/engine.py` `get_kline`
- **现象**:
  - `period='week' / 'month'` 走的是同一条路,只没截断最后 60 天
  - 实际返回的还是日 K 600 根,前端"周线/月线"按钮画出 600 个数据点
- **验收**:
  - [ ] 周 K: `df.resample('W', on='date').agg({open:'first', high:'max', low:'min', close:'last', volume:'sum'})`
  - [ ] 月 K: 同上,`resample('M', ...)`
  - [ ] 验证前端"日/周/月"切换 3 个按钮各自显示正确条数(约 60 / 100 / 36)
  - [ ] 选股系统 K 线接口响应时间 < 1 秒

### [x] P0-4 FastAPI 改 lifespan
- **位置**: `stock-picker/app.py:36`
- **现象**: `@app.on_event('startup')` 是 FastAPI 0.104+ 已废弃的写法,1.0 会移除
- **验收**:
  - [ ] 改为 `@asynccontextmanager` + `lifespan` 上下文管理器
  - [ ] 跑 `uvicorn app:app` 无 deprecation warning

### [x] P0-5 删 `routes.py` 末尾的 `init_db()`
- **位置**: `stock-picker/api/routes.py:543`
- **现象**: 模块导入时执行 `init_db()`,测试和多 worker 启动时会被并发执行
- **验收**:
  - [ ] 删掉该行,统一交给 `app.py` 的 lifespan
  - [ ] 测试 `from api.routes import router` 不再触发数据库迁移

### [x] P0-6 修 `total_mv / circ_mv` 字段错位
- **位置**:
  - `stock-picker/data/fetcher.py:280-294` (`get_quote`)
  - `stock-picker/data/store.py:680-681` (`save_quote_snapshots`)
- **现象**:
  - fetcher 里 `market_cap` 和 `circ_mktcap` **用了同一个字段** `mktcap`,流通市值永远是 0
  - store 的 SQL 用 `quote.get('market_cap')` 取值,但列名是 `total_mv / circ_mv`——SQL 语法上能跑,但**业务上永远存 0**
  - 前端详情页看不到市值
- **验收**:
  - [ ] fetcher 修正:从腾讯接口正确的字段取流通市值(查文档确认字段名)
  - [ ] store 修正:字段名对齐 schema (`total_mv / circ_mv`)
  - [ ] 跑一次 `refresh_daily_pipeline` 后,查 `stock_quote_snapshot` 的 `total_mv / circ_mv` 有非零值
  - [ ] 前端详情页"总市值 / 流通市值"卡片显示正确数字

---

## 🟠 P1 — 应改

### [x] P1-1 数据库连接改连接池
- **位置**: `stock-picker/data/store.py:168-184`
- **现象**: `@contextmanager get_cursor` 每次都 `connect + commit + close()`,5000 只股批量写慢
- **验收**:
  - [ ] 用一个长生命周期的 `Connection` + `PRAGMA journal_mode=WAL`
  - [ ] 多线程场景加 `check_same_thread=False` + 超时
  - [ ] benchmark: 5000 只 `INSERT OR REPLACE` 速度提升 ≥ 30%

### [x] P1-2 改 `INSERT OR REPLACE` 为 `ON CONFLICT DO UPDATE`
- **位置**:
  - `store.py:617-644` `save_daily_data`
  - `store.py:661-682` `save_quote_snapshots`
  - `store.py:1230-1243` `save_rps_data`
  - `store.py:525-568` `save_stock_basic`
  - `store.py:577-613` `save_stocks`(整个函数会消失,见 P1-7)
- **现象**: `INSERT OR REPLACE` 在有 `AUTOINCREMENT` 的表上会**先 DELETE 再 INSERT**,`id` 变化、外键级联失效
- **验收**:
  - [ ] 4 处全部改写为 `INSERT ... ON CONFLICT(code, date) DO UPDATE SET ...`
  - [ ] 单测: 重复保存同 `code/date` 的记录,`id` 不变,字段更新

### [x] P1-3 用集中式 schema_migrations 替换散落 ALTER (轻量化,不引 alembic 依赖)
- **位置**: `store.py:393-421` 40 行 ALTER TABLE 散落在 `init_db`
- **现象**: 每加一个字段都得手动加一行,容易漏
- **验收**:
  - [ ] 装 `alembic`,生成 `migrations/`
  - [ ] 把 `template_screen_cache` 的 20 个字段迁移纳入版本管理
  - [ ] `alembic upgrade head` 幂等可重入

### [x] P1-4 拆 `engine.py`(1386 行)
- **位置**: `stock-picker/engine.py`
- **现象**: 一个文件里塞了 screening / search / detail / kline / 缓存读 / 公式解析 / 工具方法
- **验收**:
  - [ ] 拆成 `engine/screening.py` `engine/search.py` `engine/detail.py` `engine/kline.py` `engine/cache.py` `engine/indicators.py`
  - [ ] `engine.py` 留下 `ScreeningEngine` 入口类
  - [ ] 跑现有 `bench.py` 验证接口行为不变

### [x] P1-5 `template_hits` 盘后预计算入库 (schema 加 template_hits_json + get_template_hits_for_code,详情页快路径走缓存)
- **位置**: `engine.py:546-595` `_build_template_hits` + `template_screen_cache` schema
- **现象**: 详情页每打开一只股票,实时把 4 个内置策略都重跑一遍
- **验收**:
  - [ ] `template_screen_cache` 加 `template_hits_json` 字段(或新表 `template_hits_by_code`)
  - [ ] 盘后 `run_daily_screen` 时一并写入
  - [ ] 详情页接口直接读缓存,不再调 `strategy.screen()`
  - [ ] 详情页响应 < 1 秒

### [x] P1-6 `_normalize_prev_close` 优先级明确
- **位置**: `engine.py:418-446` + `948-953`
- **现象**: 会**用 change_pct 倒推 prev_close** 覆盖数据源给的 prev_close,优先级混乱
- **验收**:
  - [ ] 优先级改为: `data_prev_close > data_change_pct_inferred > fallback`,且仅在 change_pct ∈ ±20% 才用
  - [ ] 写单测覆盖三种场景: 数据源 prev_close 正确 / 缺省 / 异常

### [x] P1-7 删 `stocks` 表,只留 `stock_basic`
- **位置**: `store.py:211-220` `447-494` `519-614` `766-823` `843-862`
- **现象**: 旧表 + 新表**双向同步**,字段不完整
- **验收**:
  - [ ] `init_db` 不再建 `stocks` 表
  - [ ] 删 `save_stocks` 函数
  - [ ] 把所有 `FROM stocks` 改为 `FROM stock_basic`
  - [ ] 写一次性迁移脚本,把旧 `stocks` 数据并入 `stock_basic`
  - [ ] 跑 `run_daily_screen`,前端数据无变化

### [x] P1-8 `scripts_refresh_latest.py` 抽公共函数
- **位置**: `scripts_refresh_latest.py:110-169` 和 `:172-236`
- **现象**: `rebuild_rps_for_latest_date` 和 `refresh_daily_pipeline` 90% 重复
- **验收**:
  - [ ] 抽 `_rebuild_rps_and_cache(latest_df, codes, latest_trade_date)` 公共函数
  - [ ] 两个入口都调用它,差异点(K 线来源)抽成参数

### [x] P1-9 4 个策略共用 `indicators.py`
- **位置**: 4 个 `strategies/*.py`
- **现象**: 4 个文件里 `_ma / _hhv / _sma / _ema / _get_rps` 全是重复实现
- **验收**:
  - [ ] 抽到 `stock-picker/indicators.py`,提供 `ma / ema / sma / hhv / llv / kdj / macd / rsi`(全部向量化)
  - [ ] 4 个策略文件全部 import 同一份,删本地重复
  - [ ] 跑 4 个策略的回归测试,命中结果一致

### [x] P1-10 排除规则统一用 `is_st` 字段
- **位置**: `config.py:56` `engine.py:43-48` `engine.py:822-853`
- **现象**: `EXCLUDE_KEYWORDS` 在 `screen()` 用,`search()` 只用 `is_st` 字段,两条路径行为不一致
- **验收**:
  - [ ] 删 `EXCLUDE_KEYWORDS`,排除逻辑全部走 `stock_basic.is_st`
  - [ ] 写脚本回填 `is_st`(基于名称里含 "ST" / "*ST")
  - [ ] 验证 `search` 和 `screen` 两条路径对"ST 股票"的处理一致

### [x] P1-11 `cache_hit` 语义修正 (区分"真有数据"和"缓存确实空"两种语义)
- **位置**: `engine.py:1091` `1103` `1111` `1119` `1135` `1145` `1167` `1235`
- **现象**: 任何路径都返回 `cache_hit=True`,前端"缓存命中"标签永远是绿色
- **验收**:
  - [ ] 区分 `cache_hit`(真有缓存数据)和 `cache_empty`(缓存存在但页空)
  - [ ] 仅在"快照非空" + "快照字段齐全"时返回 `True`
  - [ ] 前端按语义显示"缓存命中" / "交易日" / "暂无数据"

---

## 🟡 P2 — 建议改

### [ ] P2-1 加 `tests/` 目录和 pytest
- **位置**: 新建 `stock-picker/tests/`
- **验收**:
  - [ ] `requirements.txt` 加 `pytest` `pytest-asyncio` `httpx`
  - [ ] 4 个策略各写 1 个单测(用 fixture 喂入 mock DataFrame,验证命中/不命中)
  - [ ] 公式解析器单测: 4 个内置表达式
  - [ ] `engine.search` / `engine.get_kline` 各 1 个集成测试
  - [ ] CI 跑通 `pytest -q`

### [ ] P2-2 `print` 改 `logging`
- **位置**: 全文 80+ 处 `print`
- **验收**:
  - [ ] 配 `logging.basicConfig`,级别 INFO
  - [ ] 80+ 处 `print` 改 `logger.info/warning/error`
  - [ ] 关键异常走 `logger.exception`

### [x] P2-3 异常不要静默吞 (4 策略 + _ErrorCounter + scheduler 汇总)
- **位置**: 4 个 `strategies/*.py` `except Exception as e: print(...)`
- **验收**:
  - [ ] 改 `logger.warning(...)` + 计数器
  - [ ] `run_daily_screen` 跑完汇总异常数,> 阈值时 logger.error

### [x] P2-4 删 dead code (5 个脚本 + 2 个 json 标记为 DEPRECATED,运行时 raise SystemExit)
- **位置**: `stock-picker/simple_server.py` `scripts/convert_day_to_parquet.py` `scripts/pack_hs.py` `scripts/bench.py` `scripts/tencent_crosscheck.py` `scripts/data/*.json` 中无用的
- **现象**: 早期实验产物,SQLite 体系起来后已停用
- **验收**:
  - [ ] 加 `DEPRECATED.md` 标记归档,或直接删
  - [ ] `README.md` 指明只跑 `python -m stock-picker.app` 一个入口

### [ ] P2-5 fetcher 行情抓取并发化
- **位置**: `stock-picker/data/fetcher.py:258-302` `get_quote` 和 `425-480` `batch_update_daily_data`
- **现象**: 5000 只股串行 + 0.1s sleep = 8 分钟
- **验收**:
  - [ ] `concurrent.futures.ThreadPoolExecutor`,并发 10
  - [ ] 或换 `http://web.ifzqgtimg.cn/appstock/app/minute/query` 批量接口
  - [ ] benchmark: 5000 只股单日 K 线 < 60 秒

### [x] P2-6 K 线字段命名统一 (前端 K/D/J → k/d/j 对齐后端)
- **位置**: `engine.py:1303-1311`
- **现象**: `rps_history` snake_case,但 `K/D/J` 大写,`MA5/10/20/60/120/250` 大写
- **验收**:
  - [ ] 全部小写 snake_case (`k / d / j / ma5 / ma10 / ...`),和 `api/schemas.py` 风格一致
  - [ ] 前端 `KlineChart.vue` 同步改

### [x] P2-7 行情字段加 mock 兜底一致性测试 (engine._enrich_search_results 出口用 StockSearchItem Pydantic 校验)
- **位置**: `stock-picker-vue/src/data/mock.js`
- **验收**:
  - [ ] 用 `StockSearchItem` Pydantic 模型在后端 `get_cached_template_results` 出口校验
  - [ ] 缺字段立刻 `logger.warning`,不静默

### [ ] P2-8 排除 ST 用 SQL 不用字符串 contains
- **位置**: `engine.py:42-48` `59-61`
- **现象**: `stock_df['name'].str.contains('ST')` 会误伤"非 ST 但名字含 ST"的情况
- **验收**:
  - [ ] 全用 `is_st` 字段过滤,删 `EXCLUDE_KEYWORDS` 字符串匹配
  - [ ] 见 P1-10

### [ ] P2-9 加 healthz / readiness 探针
- **位置**: `api/routes.py:33`
- **现象**: 只有 `/api/health` 返回固定 JSON,没探 DB / RPS
- **验收**:
  - [ ] `/api/health/live` 返回固定 `{status: ok}`
  - [ ] `/api/health/ready` 校验 DB 连得通 + `stock_basic` 非空 + `template_screen_cache` 今日有数据

### [ ] P2-10 加 OpenAPI 描述
- **位置**: `app.py:15`
- **验收**:
  - [ ] 4 个内置模板的 `description` 接入 OpenAPI `tags` / `summary`
  - [ ] 文档在 `/docs` 显示分组

---

## 改的顺序建议

```
阶段 1(3.5 天,必跑): P0-1 → P0-5 → P0-4 → P0-6 → P0-3 → P0-2
阶段 2(5.5 天,选跑): P1-6 → P1-7 → P1-9 → P1-10 → P1-1 → P1-2
                    P1-3 → P1-4 → P1-5 → P1-8 → P1-11
阶段 3(3 天,长跑):  P2-1 → P2-2 → P2-3 → P2-4 → P2-5
                    P2-6 → P2-7 → P2-8 → P2-9 → P2-10
```

---

## 改完后怎么验收

每项打勾前,在本地跑:
```bash
cd /Volumes/N3000/AIChat/stock-system/stock-picker
python -m app                                  # 启服务
python -m scripts_refresh_latest.py --rps-only # 重建 RPS
python -m scripts_refresh_latest.py --cache-only  # 重建缓存
# 浏览器开 http://localhost:8080/docs 试 5 个端点
# 切 4 个模板,b1/s2/s3/kd1 命中数 > 0
# 详情页日/周/月 K 线 3 个按钮各自正确
```

性能基线(改完后测一次,记到 `docs/bench.md`):
- `POST /api/stocks/template-results` 全 5000 只 < 2 秒
- `GET /api/stocks/{code}` < 1 秒
- `GET /api/kline/{code}` 日/周/月 各自 < 1 秒
