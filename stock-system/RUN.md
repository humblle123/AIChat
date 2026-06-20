# Stock Picker 本地运行指南

## 前置条件

```bash
cd /Volumes/N3000/AIChat/stock-system
```

## 1. 安装依赖

### 后端
```bash
cd stock-picker
pip install -r requirements.txt
```

### 前端
```bash
cd ../stock-picker-vue
npm install
```

## 2. 数据导入

### 2.1 初始化数据库 + 导入股票池(5500 只)
```bash
cd /Volumes/N3000/AIChat/stock-system

# 用临时目录存放数据库文件(推荐,避免污染仓里 data/ 目录)
export PICKER_DB_DIR=/tmp/picker_db
mkdir -p $PICKER_DB_DIR

# 导入股票基础信息(从腾讯列表同步 5500 只 A 股)
python3 -c "
import sys; sys.path.insert(0, 'stock-picker')
from data.fetcher import sync_stock_basic_from_local_cache
n = sync_stock_basic_from_local_cache('data/tencent_hs.json')
print(f'导入 {n} 只股票')
"
```

### 2.2 导入历史 K 线(约 2-5 分钟)
```bash
# 从通达信 .day 文件导入 5500 只股票 × 6000+ 根日 K 线
python3 scripts/import_hsjday_to_sqlite.py
# 预期输出: imported_codes=~4800 imported_rows=~3800万 missing_files=~500 total_codes=5481
```

### 2.3 重建 RPS + 模板缓存
```bash
cd stock-picker
# RPS 重建(基于历史 K 线的收盘价计算 50/120/250 日相对强弱排名)
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --rps-only
# 模板缓存重建(跑 b1/s2/s3/kd1 4 个策略,结果落库缓存)
PICKER_DB_DIR=/tmp/picker_db python3 scripts_refresh_latest.py --cache-only
```

## 3. 启动

### 后端服务
```bash
cd /Volumes/N3000/AIChat/stock-system/stock-picker
PICKER_DB_DIR=/tmp/picker_db python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```
看到以下日志说明启动成功:
```
[日期 时间] INFO    app: 初始化数据库...
[DB] 数据库初始化完成
[日期 时间] INFO    app: Smart Stock Picker 启动完成
```

### 前端
新开一个终端:
```bash
cd /Volumes/N3000/AIChat/stock-system/stock-picker-vue
npm run dev
```
浏览器打开 http://localhost:5173

## 4. 验证

后端启动后,在浏览器打开 http://localhost:8080/docs 可以看到自动生成的 OpenAPI 文档,
包含 4 个标签组(templates / search / detail / health),所有接口都可直接在线调试。

或者用 curl 快速验证:
```bash
# 健康检查
curl http://localhost:8080/api/health/ready

# 模板列表(4 个内置策略)
curl http://localhost:8080/api/formula/templates | python3 -m json.tool

# 股票详情(选一个 A 股,如 000001 平安银行)
curl http://localhost:8080/api/stocks/000001 | python3 -m json.tool

# K 线(日/周/月)
curl 'http://localhost:8080/api/kline/000001?period=day' | python3 -m json.tool

# 公式校验
curl -X POST http://localhost:8080/api/formula/validate \
  -H 'Content-Type: application/json' \
  -d '{"formula": "RPS50 > 85 AND RPS120 > 88"}'

# 公式搜索
curl -X POST http://localhost:8080/api/stocks/search \
  -H 'Content-Type: application/json' \
  -d '{"formula":"RPS50 > 85 AND RPS120 > 88","page_size":5,"sort_by":"rps50","sort_order":"desc"}'

# 模板结果
curl -X POST http://localhost:8080/api/stocks/template-results \
  -H 'Content-Type: application/json' \
  -d '{"template_id":3,"page":1,"page_size":10}'

# 基础筛选
curl -X POST http://localhost:8080/api/stocks/search \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"银行","page_size":5,"sort_by":"total_mv","sort_order":"desc"}'
```

## 5. 运行测试(70 个)
```bash
cd /Volumes/N3000/AIChat/stock-system/stock-picker
PICKER_DB_DIR=/tmp python3 -m pytest tests/ -v
# 预期: 70 passed
```

## 6. 性能测试
```bash
cd /Volumes/N3000/AIChat/stock-system/stock-picker
PICKER_DB_DIR=/tmp/picker_db python3 stock-picker/scripts/bench.py
```

## 常见问题

### `disk I/O error` 或 `database is locked`
- 沙箱/虚拟挂载文件系统不支持 WAL 模式,代码已自动降级(见 `store.py` PRAGMA 部分)
- 如果发生在 Mac 本地,检查磁盘空间(`stocks.db` 全量约 2.5~3GB)

### 前端代理 404
- `stock-picker-vue/vite.config.js` 默认代理 `http://127.0.0.1:8080/api`
- 确认后端端口和配置一致

### 模板命中为 0
- 只有跑过 `--cache-only` 后缓存才有数据
- 如果刚导入 K 线但没重建 RPS,RPS 字段为空,模板依赖 RPS 的策略(s2/s3/kd1)不会命中
