# 选股系统需求文档

## 1. 项目概述

### 1.1 项目名称
**Smart Stock Picker** - 智能选股系统

### 1.2 项目背景
当前 A 股市场股票数量众多，个人投资者很难快速筛出符合自己策略的股票。现有工具往往要么偏资讯浏览，要么偏专业终端，缺少一个面向个人研究者、能直接用公式进行选股并查看详情的轻量系统。

本项目目标是建设一个可落地的选股系统，支持用户通过结构化条件和选股公式筛选股票，并查看股票详情页中的行情、K 线和核心基本面信息。

### 1.3 一期目标
- 支持股票池筛选
- 支持类通达信风格的可执行选股公式筛选
- 支持结果排序、分页和详情页查看
- 支持前端页面与 Python 后端联动
- 为二期评分模型、回测和自选股能力预留扩展空间

### 1.4 目标用户
- 个人投资者
- 量化投资爱好者
- 投资研究学习者

## 2. 产品范围

### 2.1 一期范围（必须交付）

#### 2.1.0 股票池范围
- 仅纳入 A 股普通股票
- 纳入范围：沪 A、深 A、创业板、科创板
- 不纳入：北交所
- 不纳入：ETF
- 不纳入：可转债、国债、企业债等债券类品种
- 不纳入：已退市股票
- 默认排除：ST 股票，但允许用户勾选纳入
- 默认排除：停牌股票

#### 2.1.1 股票筛选
- 市场选择：沪 A、深 A、创业板、科创板
- 行业筛选：申万一级行业，多选
- 概念板块筛选：多选
- 股票代码/名称搜索
- 总市值范围
- 流通市值范围
- 上市天数下限
- 最近一个交易日涨跌幅范围
- ST / 停牌排除开关

#### 2.1.2 公式选股
- 用户可输入类通达信风格公式进行筛选
- 一期目标是“常用选股公式兼容”，不是完整复刻通达信全部语法
- 支持逻辑运算：`AND`、`OR`、`NOT`
- 支持比较运算：`>`、`>=`、`<`、`<=`、`=`、`!=`
- 支持括号分组
- 支持类通达信字段别名与标准字段映射，例如：
  - `CLOSE` -> `close`
  - `OPEN` -> `open`
  - `HIGH` -> `high`
  - `LOW` -> `low`
  - `VOL` -> `volume`
  - `KDJ_K` -> `kdj_k`
  - `KDJ_D` -> `kdj_d`
  - `KDJ_J` -> `kdj_j`
  - `RPS50` -> `rps50`
  - `RPS120` -> `rps120`
  - `RPS250` -> `rps250`
- 支持常用字段引用，例如：
  - `pe_ttm`
  - `pb`
  - `roe_ttm`
  - `revenue_yoy_q`
  - `net_profit_yoy_q`
  - `turnover_rate`
  - `volume_ratio_1d`
  - `ma5`
  - `ma10`
  - `ma20`
  - `ma60`
  - `rsi14`
  - `macd_dif`
  - `macd_dea`
  - `macd_hist`
- 支持常用技术公式函数：
  - `MA(X, N)`
  - `EMA(X, N)`
  - `REF(X, N)`
  - `COUNT(X, N)`
  - `HHV(X, N)`
  - `LLV(X, N)`
  - `CROSS(A, B)`
- 支持预置公式模板：
  - 低估值
  - 高成长
  - 均线多头
  - 放量突破
- 支持内置策略模板库，优先整合以下策略：
  - `b1` 空谷幽兰：`J < 18` 且 `CLOSE > 多空线` 且 `多头线 > 空头线`
  - `s2` 月线反转：`站上年线` 且 `30日内50日新高` 且 `RPS50 >= 85`
  - `s3` RPS三线红：`RPS50 > 90` 且 `RPS120 > 93` 且 `RPS250 > 95` 且 `接近250日高点`
  - `kd1` 一线红：`任一RPS > 95` 且 `距250日高点 < 40%`
- 内置策略模板来源于 `ai-project/stock-board` 的现有策略实现，可作为一期默认模板
- 筛选时支持按策略分组过滤：
  - `技术面`
  - `月线反转`
  - `RPS红系`
  - `一线红`
  - `三线红`
- 其中 `一线红(kd1)` 归入 `RPS红系` 的子分组，前端可单独筛选，也可作为 `RPS红系` 的组成项一起展示
- 支持公式校验与错误提示

#### 2.1.3 结果列表
- 展示字段：
  - 股票代码
  - 股票名称
  - 所属市场
  - 所属行业
  - 最近收盘价
  - 最近一个交易日涨跌幅
  - 总市值
  - 流通市值
  - PE(TTM)
  - PB
  - ROE(TTM)
  - 营收同比
  - 净利润同比
- 支持列排序
- 支持分页：20 / 50 / 100
- 支持显示总命中数量
- 支持点击行进入详情页

#### 2.1.4 股票详情页
- 股票基本信息：
  - 代码
  - 名称
  - 市场
  - 行业
  - 上市日期
- 行情信息：
  - 最近收盘价
  - 涨跌额
  - 最近一个交易日涨跌幅
  - 成交额
  - 成交量
  - 换手率
- K 线图：
  - 日 K
  - 周 K
  - 月 K
  - MA5 / MA10 / MA20 / MA60
- 核心财务卡片：
  - PE(TTM)
  - PB
  - ROE(TTM)
  - 营收同比
  - 净利润同比
  - 资产负债率
- 技术指标卡片：
  - RSI(14)
  - MACD(12,26,9)
  - 量比

#### 2.1.5 后端服务
- 提供统一 REST API 给前端调用
- 负责第三方数据采集、清洗、计算和缓存
- 负责公式解析与筛选执行
- 负责 K 线和指标计算

### 2.2 二期范围（明确不在本期交付）
- 多因子综合评分模型
- 历史回测
- 条件预警
- 新闻公告聚合
- 自然语言选股

## 3. 架构决策

### 3.1 总体架构
- 前端：单页应用
- 后端：Python 服务
- 数据层：本地数据库 + 本地缓存文件
- 数据源：第三方行情与财务数据源

### 3.2 前端职责
- 提供筛选界面和公式编辑区
- 展示选股结果
- 展示股票详情页和 K 线图
- 管理筛选条件、分页、排序等状态

### 3.3 Python 后端职责
- 拉取股票基础资料、行情、K 线、财务指标
- 标准化不同数据源字段
- 预计算技术指标
- 执行公式解析和过滤
- 向前端输出统一口径的数据结构

### 3.4 为什么不用纯前端
- 第三方数据接口可能存在 CORS、限流和不稳定问题
- 财务与技术指标需要统一计算口径
- 公式执行和数据清洗更适合放在 Python 后端
- 后续回测、评分、预警能力也更适合沿用同一后端

## 4. 数据源策略

### 4.1 一期数据源原则
- 以后端采集为主，前端不直接调用第三方行情接口
- 免费数据源可作为 MVP 方案，但必须经过后端统一封装
- 所有字段以系统内部标准字段名输出，前端不感知第三方源差异
- 数据更新以每日盘后批量更新为准，不做盘中刷新

### 4.2 推荐数据源分工
- 实时/准实时行情：腾讯财经
- 历史 K 线：腾讯财经
- 基础资料与补充财务：AKShare
- 行业分类：申万一级行业
- 概念板块：东方财富或 AKShare 可获取的板块映射

### 4.3 更新频率
- 基础资料：每日更新
- 日线和周线：每日收盘后更新
- 行情快照：每日收盘后更新
- 财务数据：按季更新

## 5. 指标口径统一清单

这一节是一期开发必须统一的核心规则。后端、前端和公式引擎全部以本节为准。

### 5.1 基础字段口径
- `market`
  - 取值限定：`SHA`、`SZA`、`CYB`、`KCB`
- `listed_date`
  - 使用股票首次上市日期
- `listed_days`
  - 计算方式：`当前交易日 - listed_date`
- `industry`
  - 一期固定使用申万一级行业
- `concept_tags`
  - 概念板块标签列表
  - 可多值存储，但前端展示应限制数量，避免结果列表过宽
- `security_type`
  - 一期只允许 `stock`
- `is_delisted`
  - 退市股票不纳入股票池

### 5.2 行情字段口径
- `price`
  - 最近一个交易日收盘价；若停牌则取最近有效收盘价，并额外标注停牌状态
- `change_pct`
  - 计算方式：`(最近收盘价 - 前收盘价) / 前收盘价 * 100`
- `turnover_rate`
  - 使用当日换手率，单位为百分比
- `volume`
  - 当日成交量，原始单位统一为股
- `amount`
  - 当日成交额，原始单位统一为元

### 5.3 估值字段口径
- `pe_ttm`
  - 使用滚动 12 个月市盈率
  - 亏损公司允许返回负值或空值，但展示与筛选规则要统一处理
- `pb`
  - 使用最新市净率
- `peg`
  - 计算方式：`pe_ttm / net_profit_yoy_q`
  - 当 `net_profit_yoy_q <= 0` 时，`peg` 记为 `null`

### 5.4 财务字段口径
- `roe_ttm`
  - 使用滚动 12 个月净资产收益率
- `revenue_yoy_q`
  - 使用最近披露季度的营业收入同比增长率
- `net_profit_yoy_q`
  - 使用最近披露季度的归母净利润同比增长率
- `debt_ratio`
  - 使用最近披露季度资产负债率
- `report_period`
  - 使用最近一期财报期，例如 `2025Q4`

### 5.5 均线字段口径
- `ma5`
  - 最近 5 个交易日收盘价均值
- `ma10`
  - 最近 10 个交易日收盘价均值
- `ma20`
  - 最近 20 个交易日收盘价均值
- `ma60`
  - 最近 60 个交易日收盘价均值

### 5.6 MACD 字段口径
- 参数固定：`12, 26, 9`
- `macd_dif`
  - 12 日 EMA 与 26 日 EMA 差值
- `macd_dea`
  - `macd_dif` 的 9 日 EMA
- `macd_hist`
  - `2 * (macd_dif - macd_dea)`
- `macd_golden_cross`
  - 当日 `macd_dif` 上穿 `macd_dea`
- `macd_dead_cross`
  - 当日 `macd_dif` 下穿 `macd_dea`

### 5.7 RSI 字段口径
- 参数固定：`14`
- `rsi14`
  - 14 日 RSI
- 超买阈值默认：`70`
- 超卖阈值默认：`30`

### 5.8 成交量相关字段口径
- `volume_ratio_1d`
  - 计算方式：`当日成交量 / 过去 5 个交易日日均成交量`
- `avg_volume_5d`
  - 最近 5 个交易日平均成交量

### 5.9 RPS 字段口径
- `rps5`
- `rps10`
- `rps15`
- `rps20`
- `rps50`
- `rps120`
- `rps250`
- 含义：某周期收益率在全市场股票中的百分位排名，取值 `0~100`
- 更新频率：每日盘后批量更新
- 一期优先支持 `rps50`、`rps120`、`rps250`，用于内置策略模板

### 5.10 公式引擎中的空值规则
- 空值字段默认不命中数值比较条件
- 例如 `peg < 1` 中，若 `peg = null`，则该条件返回 `false`
- 所有空值规则需要在前端公式帮助中说明

### 5.11 KDJ 字段口径
- `kdj_k`
  - 参数固定：`9, 3, 3`
- `kdj_d`
  - 9 日 RSV 的 3 日平滑值
- `kdj_j`
  - 计算方式：`3 * kdj_k - 2 * kdj_d`
- `KDJ` 相关字段一期用于 `b1` 模板和相关筛选条件

## 6. 功能需求

### 6.1 选股页
- 左侧为基础筛选面板
- 中部为公式编辑器或公式模板区
- 右侧或下方为结果列表
- 支持以下交互：
  - 重置条件
  - 执行筛选
  - 切换模板
  - 排序
  - 翻页

### 6.2 详情页
- 顶部为股票摘要区
- 中部为 K 线图与技术指标
- 下部为财务摘要
- 一期不要求新闻、公告和社区内容

### 6.3 公式兼容策略
- 一期采用“类通达信兼容”方案
- 优先兼容常见选股公式，而非全部绘图、预警、跨周期和脚本能力
- 一期优先支持以下常用函数：
  - `MA(X, N)`
  - `EMA(X, N)`
  - `REF(X, N)`
  - `COUNT(X, N)`
  - `HHV(X, N)`
  - `LLV(X, N)`
  - `CROSS(A, B)`
- 一期不支持：
  - 画线类函数
  - 图标绘制类函数
  - 交易信号回测语义
  - 分钟级周期
  - 自定义脚本副作用

### 6.4 内置模板公式
- `b1` 空谷幽兰
  - `KDJ_J < 18 AND CLOSE > ZXDQ AND ZXDQ > ZXDKX`
  - 其中：
    - `ZXDQ = EMA(EMA(CLOSE, 10), 10)`
    - `ZXDKX = (MA(CLOSE, 14) + MA(CLOSE, 28) + MA(CLOSE, 57) + MA(CLOSE, 114)) / 4`
- `s2` 月线反转
  - `CLOSE > MA(CLOSE, 250) AND COUNT(HIGH >= HHV(HIGH, 50), 30) > 0 AND RPS50 >= 85 AND COUNT(CLOSE > MA(CLOSE, 250), 30) > 2 AND COUNT(CLOSE > MA(CLOSE, 250), 30) < 30 AND CLOSE / HHV(HIGH, 100) > 0.9`
- `s3` RPS三线红
  - `RPS50 > 90 AND RPS120 > 93 AND RPS250 > 95 AND CLOSE / HHV(HIGH, 250) > 0.85`
- `kd1` 一线红
  - `(RPS50 > 95 OR RPS120 > 95 OR RPS250 > 95) AND CLOSE / HHV(HIGH, 250) > 0.6`
- 一期模板公式按“可读、可改、可复用”的原则实现，后端需要支持公式参数化和模板别名映射
- 模板分组建议：
  - `技术面`: `b1`
  - `月线反转`: `s2`
  - `RPS红系`: `s3`、`kd1`
  - `三线红`: `s3`
  - `一线红`: `kd1`

## 7. API 草案

### 7.1 股票筛选接口
- `POST /api/stocks/search`
- 请求体包含：
  - `markets`
  - `industries`
  - `concepts`
  - `keyword`
  - `filters`
  - `formula`
  - `template_id`
  - `template_params`
  - `sort_by`
  - `sort_order`
  - `page`
  - `page_size`
- `filters` 建议结构：
  - `min_total_mv`
  - `max_total_mv`
  - `min_circ_mv`
  - `max_circ_mv`
  - `min_listed_days`
  - `max_change_pct`
  - `min_change_pct`
  - `include_st`
  - `exclude_suspended`
- 返回结构：
  - `items`
  - `page`
  - `page_size`
  - `total`
  - `applied_formula`
  - `applied_template`

### 7.2 股票详情接口
- `GET /api/stocks/{code}`
- 返回结构建议：
  - `basic`
  - `quote`
  - `fundamentals`
  - `technicals`
  - `kline_summary`
  - `template_hits`

### 7.3 K 线接口
- `GET /api/stocks/{code}/kline?period=day|week|month`
- 返回结构建议：
  - `code`
  - `period`
  - `data`
  - `ma_lines`
  - `last_trade_date`

### 7.4 公式校验接口
- `POST /api/formula/validate`
- 请求体建议：
  - `formula`
  - `template_id`
  - `template_params`
- 返回结构建议：
  - `valid`
  - `errors`
  - `normalized_formula`
  - `used_fields`

### 7.5 公式模板接口
- `GET /api/formula/templates`
- 返回结构建议：
  - `id`
  - `strategy_id`
  - `name`
  - `group`
  - `description`
  - `expression`
  - `params_schema`
  - `tags`
  - `enabled`

### 7.6 策略列表接口
- `GET /api/strategies`
- 用于前端展示可选策略组和内置模板
- 返回结构建议：
  - `id`
  - `name`
  - `group`
  - `description`
  - `templates`

## 8. 数据模型拆分

### 8.1 股票基础信息 `stock_basic`
- `code`
- `name`
- `market`
- `industry`
- `concept_tags`
- `security_type`
- `listed_date`
- `is_delisted`
- `is_st`
- `is_suspended`

### 8.2 行情快照 `stock_quote_snapshot`
- `code`
- `trade_date`
- `price`
- `prev_close`
- `change_pct`
- `volume`
- `amount`
- `turnover_rate`
- `total_mv`
- `circ_mv`

### 8.3 财务指标快照 `stock_fundamental_snapshot`
- `code`
- `report_period`
- `pe_ttm`
- `pb`
- `peg`
- `roe_ttm`
- `revenue_yoy_q`
- `net_profit_yoy_q`
- `debt_ratio`

### 8.4 技术指标快照 `stock_technical_snapshot`
- `code`
- `trade_date`
- `ma5`
- `ma10`
- `ma20`
- `ma60`
- `rsi14`
- `macd_dif`
- `macd_dea`
- `macd_hist`
- `macd_golden_cross`
- `macd_dead_cross`
- `volume_ratio_1d`
- `avg_volume_5d`

### 8.5 K 线明细 `stock_kline`
- `code`
- `period`
- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`

### 8.6 公式模板 `formula_template`
- `id`
- `strategy_id`
- `name`
- `group`
- `description`
- `expression`
- `params_schema`
- `tags`
- `enabled`
- `source`

### 8.7 用户已保存策略 `saved_strategy`
- `id`
- `name`
- `filters_json`
- `formula`
- `created_at`
- `updated_at`

说明：
- 一期只保留保存策略相关接口定义，不做页面入口和前端功能
- 如果后续需要登录体系，再补用户维度和权限控制

## 9. 非功能需求

### 9.1 性能
- 在 5000 只股票规模下，单次筛选接口目标响应时间小于 2 秒
- 详情页首屏接口目标响应时间小于 1 秒
- K 线接口返回时间目标小于 1 秒

### 9.2 可维护性
- 前后端字段命名统一
- 所有筛选字段必须在后端有唯一口径定义
- 公式字段列表必须与后端计算字段一致

### 9.3 兼容性
- PC 优先
- 现代浏览器支持：Chrome、Edge、Safari
- 移动端本期只要求可读，不要求完整交互优化

### 9.4 安全
- 前端不直接暴露第三方数据源凭证
- 所有第三方数据访问经由 Python 后端
- 本地配置文件中的密钥不得提交到仓库

### 9.5 数据时效
- 一期仅要求每日盘后更新
- 不要求盘中实时刷新
- 页面需明确展示数据所属交易日

## 10. 里程碑

| 阶段 | 时间 | 目标 |
|------|------|------|
| 需求确认 | Day 1 | 文档评审并冻结一期范围 |
| 架构落地 | Day 2 | 前端 + Python 接口方案确定 |
| 数据打通 | Week 1 | 股票池、行情、K 线、财务字段打通 |
| MVP 选股页 | Week 2 | 基础筛选 + 公式筛选 + 结果列表 |
| 详情页 | Week 3 | 股票详情 + K 线 + 指标卡片 |
| 稳定化 | Week 4 | 口径校验、性能优化、问题修复 |

## 11. 风险与依赖

### 11.1 数据风险
- 免费数据源字段不稳定
- 不同数据源之间存在口径不一致
- 个别数据源在盘后更新时点可能不一致

### 11.2 技术风险
- 公式解析器需要控制复杂度，避免一期做成通用脚本引擎
- 技术指标预计算与筛选性能需要平衡
- K 线与详情数据可能存在多源对齐问题

### 11.3 合规风险
- 系统仅作研究与选股辅助，不构成投资建议
- 页面需展示免责声明
- 后续如接入新闻和公告，需要进一步确认版权与展示边界

## 12. 结论

- 一期范围已冻结：只做接口，不做保存策略页面入口
- 内置模板已固定为 `b1` 空谷幽兰、`s2` 月线反转、`s3` RPS三线红、`kd1` 一线红
- 后端接口按“选股搜索 / 股票详情 / K线 / 公式校验 / 模板列表 / 策略列表”六类拆分
