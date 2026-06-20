"""Smart Stock Picker - FastAPI 主入口"""
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from api.schemas import API_TAGS_METADATA
from data.store import init_db
from logger import setup_logging, get_logger
from scheduler import start_scheduler

logger = get_logger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库，并启动定时任务。"""
    setup_logging()
    logger.info('初始化数据库...')
    init_db()
    global _scheduler
    _scheduler = start_scheduler()
    logger.info('Smart Stock Picker 启动完成（定时任务已接入）')
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info('定时任务已关闭')


# 创建 FastAPI 应用
app = FastAPI(
    title='Smart Stock Picker',
    description=(
        '## Smart Stock Picker API\n\n'
        '智能选股系统。一期支持:\n'
        '- 4 个内置策略模板(b1/s2/s3/kd1)与类通达信公式编辑\n'
        '- 股票池基础筛选 + 公式筛选 + 排序分页\n'
        '- 详情页(行情 / K 线 / 财务 / 技术指标)\n\n'
        '所有公开端点以 `/api` 为前缀,详细字段口径见 `/docs`。'
    ),
    version='1.0.0',
    openapi_tags=API_TAGS_METADATA,
    lifespan=lifespan,
)

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 注册路由
app.include_router(router, prefix='/api')

FRONTEND_PATH = Path(__file__).resolve().parent.parent / 'stock-picker-frontend.html'


@app.get('/')
async def root():
    return {
        'name': 'Smart Stock Picker',
        'version': '1.0.0',
        'docs': '/docs',
    }


@app.get('/api')
@app.get('/api/')
async def api_entry():
    """前端入口，保持浏览器中的 /api 地址可直接打开页面。"""
    if FRONTEND_PATH.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(FRONTEND_PATH), media_type='text/html')
    return {
        'name': 'Smart Stock Picker',
        'version': '1.0.0',
        'docs': '/docs',
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)
