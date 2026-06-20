# AIChat

AI + 量化实验仓库。

## 项目

### [stock-system](./stock-system/)

智能选股系统 — A 股选股工具，支持类通达信公式、4 个内置策略（空谷幽兰/月线反转/RPS三线红/一线红）、K 线详情、向量化筛选。

- **后端** Python 3.11 / FastAPI / SQLite / Pandas
- **前端** Vue 3 / Pinia / TailwindCSS / lightweight-charts
- **数据** 腾讯财经 + AKShare + 通达信 .day
- 5481 只全市场筛选 ~100ms，详情页 ~43ms

```
cd stock-picker && pip install -r requirements.txt
export PICKER_DB_DIR=/tmp/picker_db
uvicorn app:app --host 0.0.0.0 --port 8080
```

### hello_agent

Python AI agent 实验（OpenAI client、ReAct、PlanAndSolve 模式）。

### yao-agent

Spring Boot 3.5 / Java 21 后端项目。

### shangpinfenxi

商品分析项目（开发中）。

### kuangjia

框架实验占位目录。
