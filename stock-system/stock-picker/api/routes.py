"""API 路由"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from api.schemas import (
    ScreenRequest, ScreenResponse, StockSignal, StrategyResult,
    KLineResponse, QuoteResponse, StrategyInfo, FormulaResponse,
    FormulaTemplateResponse,
    FormulaCreate, FormulaUpdate, ScreenResultResponse,
    StockSearchRequest, StockSearchResponse, StockSearchItem, TemplateResultSummary,
    StockDetailResponse, StockDetailBasic, StockDetailQuote,
    StockDetailFundamentals, StockDetailTechnicals, StockDetailKLineSummary,
    StockTemplateHit,
    FormulaValidateRequest, FormulaValidateResponse,
)
from strategies import list_strategies
from engine import ScreeningEngine
from data.fetcher import get_quote
from data.store import (
    get_formulas, get_formula_by_id, create_formula,
    update_formula, delete_formula, get_screen_history,
    get_latest_screen_results, save_screen_result,
    get_formula_templates, get_formula_template_by_id,
    get_template_screen_summary
)
from formula_engine import validate as validate_formula, evaluate_formula, FormulaError
from config import STRATEGY_DEFAULTS
from datetime import date

router = APIRouter()
engine = ScreeningEngine()


# ====== 健康检查 ======

@router.get('/health')
async def health_check():
    """健康检查(liveness)"""
    return {'status': 'ok', 'service': 'Smart Stock Picker'}


@router.get('/health/live')
async def health_live():
    """K8s liveness probe: 进程能响应就 OK。"""
    return {'status': 'alive'}


@router.get('/health/ready')
async def health_ready():
    """K8s readiness probe: DB 连得通 + stock_basic 有数据 + 今日模板缓存有数据。"""
    from data.store import get_conn, get_latest_date, get_template_screen_summary
    checks: Dict[str, Any] = {}
    try:
        conn = get_conn()
        cur = conn.execute('SELECT COUNT(*) FROM stock_basic')
        checks['stock_basic_count'] = cur.fetchone()[0]
    except Exception as e:
        checks['db_error'] = str(e)
    checks['latest_trade_date'] = get_latest_date()
    summaries = get_template_screen_summary()
    checks['template_cached_count'] = len(summaries)
    ok = 'db_error' not in checks and checks.get('stock_basic_count', 0) > 0
    return {'status': 'ready' if ok else 'not_ready', **checks}


# ====== 公式管理 API ======

@router.get('/formulas', response_model=List[FormulaResponse])
async def list_formulas():
    """获取所有公式"""
    formulas = get_formulas()
    return [
        FormulaResponse(
            id=f['id'],
            name=f['name'],
            description=f.get('description', ''),
            code=f.get('code', ''),
            params=f.get('params', {}),
            is_active=bool(f.get('is_active', 1)),
            created_at=f.get('created_at', ''),
            updated_at=f.get('updated_at', '')
        )
        for f in formulas
    ]


@router.get('/formulas/{formula_id}', response_model=FormulaResponse)
async def get_formula(formula_id: int):
    """获取单个公式"""
    f = get_formula_by_id(formula_id)
    if not f:
        raise HTTPException(status_code=404, detail='公式不存在')
    return FormulaResponse(
        id=f['id'],
        name=f['name'],
        description=f.get('description', ''),
        code=f.get('code', ''),
        params=f.get('params', {}),
        is_active=bool(f.get('is_active', 1)),
        created_at=f.get('created_at', ''),
        updated_at=f.get('updated_at', '')
    )


@router.post('/formulas', response_model=FormulaResponse)
async def add_formula(formula: FormulaCreate):
    """创建新公式"""
    formula_id = create_formula(
        name=formula.name,
        description=formula.description or '',
        code=formula.code or '',
        params=formula.params or {}
    )
    f = get_formula_by_id(formula_id)
    return FormulaResponse(
        id=f['id'],
        name=f['name'],
        description=f.get('description', ''),
        code=f.get('code', ''),
        params=f.get('params', {}),
        is_active=bool(f.get('is_active', 1)),
        created_at=f.get('created_at', ''),
        updated_at=f.get('updated_at', '')
    )


@router.put('/formulas/{formula_id}', response_model=FormulaResponse)
async def modify_formula(formula_id: int, formula: FormulaUpdate):
    """更新公式"""
    existing = get_formula_by_id(formula_id)
    if not existing:
        raise HTTPException(status_code=404, detail='公式不存在')
    
    update_formula(
        formula_id=formula_id,
        name=formula.name,
        description=formula.description,
        code=formula.code,
        params=formula.params
    )
    
    f = get_formula_by_id(formula_id)
    return FormulaResponse(
        id=f['id'],
        name=f['name'],
        description=f.get('description', ''),
        code=f.get('code', ''),
        params=f.get('params', {}),
        is_active=bool(f.get('is_active', 1)),
        created_at=f.get('created_at', ''),
        updated_at=f.get('updated_at', '')
    )


@router.delete('/formulas/{formula_id}')
async def remove_formula(formula_id: int):
    """删除公式"""
    existing = get_formula_by_id(formula_id)
    if not existing:
        raise HTTPException(status_code=404, detail='公式不存在')
    
    if delete_formula(formula_id):
        return {'message': '公式已删除', 'id': formula_id}
    raise HTTPException(status_code=500, detail='删除失败')


# ====== 内置策略模板 API ======

@router.get('/formula/templates', response_model=List[FormulaTemplateResponse])
async def list_formula_templates():
    """获取所有内置策略模板"""
    templates = get_formula_templates()
    return [
        FormulaTemplateResponse(
            id=t['id'],
            strategy_id=t['strategy_id'],
            name=t['name'],
            group_name=t.get('group_name', ''),
            description=t.get('description', ''),
            expression=t.get('expression', ''),
            params_schema=t.get('params_schema', {}),
            tags=t.get('tags', []),
            enabled=bool(t.get('enabled', 1)),
            source=t.get('source', ''),
            created_at=t.get('created_at', ''),
            updated_at=t.get('updated_at', '')
        )
        for t in templates
    ]


@router.get('/formula/templates/{template_id}', response_model=FormulaTemplateResponse)
async def get_formula_template(template_id: int):
    """获取单个内置策略模板"""
    t = get_formula_template_by_id(template_id)
    if not t:
        raise HTTPException(status_code=404, detail='模板不存在')
    return FormulaTemplateResponse(
        id=t['id'],
        strategy_id=t['strategy_id'],
        name=t['name'],
        group_name=t.get('group_name', ''),
        description=t.get('description', ''),
        expression=t.get('expression', ''),
        params_schema=t.get('params_schema', {}),
        tags=t.get('tags', []),
        enabled=bool(t.get('enabled', 1)),
        source=t.get('source', ''),
        created_at=t.get('created_at', ''),
        updated_at=t.get('updated_at', '')
    )


@router.post('/formula/validate', response_model=FormulaValidateResponse)
async def validate_formula_endpoint(request: FormulaValidateRequest):
    """校验公式可解析性,返回引用字段。"""
    formula = (request.formula or '').strip()
    if not formula and request.template_id:
        template = get_formula_template_by_id(int(request.template_id))
        formula = (template or {}).get('expression', '')
    if not formula:
        return FormulaValidateResponse(
            valid=False, errors=['公式为空'], used_fields=[], normalized_formula=''
        )
    result = validate_formula(formula)
    return FormulaValidateResponse(**result)


# ====== 选股结果 API ======

@router.get('/screen-results', response_model=Dict[int, List[ScreenResultResponse]])
async def list_screen_results():
    """获取最新的选股结果（按公式分组）"""
    results = get_latest_screen_results()
    return {
        formula_id: [
            ScreenResultResponse(
                id=r['id'],
                date=r['date'],
                formula_id=r['formula_id'],
                formula_name=r.get('formula_name', ''),
                code=r['code'],
                name=r.get('name', ''),
                reason=r.get('reason', ''),
                metadata=r.get('metadata', {})
            )
            for r in stocks
        ]
        for formula_id, stocks in results.items()
    }


@router.get('/screen-results/history')
async def screen_history(date: str = None, formula_id: int = None):
    """获取历史选股结果"""
    results = get_screen_history(date=date, formula_id=formula_id)
    return [
        ScreenResultResponse(
            id=r['id'],
            date=r['date'],
            formula_id=r['formula_id'],
            formula_name=r.get('formula_name', ''),
            code=r['code'],
            name=r.get('name', ''),
            reason=r.get('reason', ''),
            metadata=r.get('metadata', {})
        )
        for r in results
    ]


@router.post('/screen/{formula_id}')
async def screen_by_formula(formula_id: int):
    """根据公式执行选股"""
    f = get_formula_by_id(formula_id)
    if not f:
        raise HTTPException(status_code=404, detail='公式不存在')
    
    # 执行选股
    result = engine.screen([f['code']], {'params': f.get('params', {})})
    
    today = date.today().isoformat()
    
    # 保存结果
    if result.get('signals'):
        save_screen_result(today, formula_id, result['signals'])
    
    return {
        'date': today,
        'formula_id': formula_id,
        'formula_name': f['name'],
        'count': len(result.get('signals', [])),
        'signals': result.get('signals', [])
    }


# ====== 原有 API ======

@router.get('/strategies', response_model=List[StrategyInfo])
async def get_strategies():
    """获取策略列表"""
    strategies = list_strategies()
    templates = get_formula_templates()
    templates_by_strategy = {}
    for template in templates:
        templates_by_strategy.setdefault(template['strategy_id'], []).append(template)

    return [
        StrategyInfo(
            id=s['id'],
            name=s['name'],
            description=s['description'],
            group=(templates_by_strategy.get(s['id'], [{}])[0].get('group_name', '') if templates_by_strategy.get(s['id']) else ''),
            template_count=len(templates_by_strategy.get(s['id'], [])),
            templates=[
                FormulaTemplateResponse(
                    id=t['id'],
                    strategy_id=t['strategy_id'],
                    name=t['name'],
                    group_name=t.get('group_name', ''),
                    description=t.get('description', ''),
                    expression=t.get('expression', ''),
                    params_schema=t.get('params_schema', {}),
                    tags=t.get('tags', []),
                    enabled=bool(t.get('enabled', 1)),
                    source=t.get('source', ''),
                    created_at=t.get('created_at', ''),
                    updated_at=t.get('updated_at', '')
                )
                for t in templates_by_strategy.get(s['id'], [])
            ],
            params=STRATEGY_DEFAULTS.get(s['id'])
        )
        for s in strategies
    ]


@router.post('/screen', response_model=ScreenResponse)
async def screen_stocks(request: ScreenRequest):
    """
    执行选股
    - strategies: 策略列表，如 ['b1', 's3']
    - params: 各策略参数，如 {'s3': {'min_rps50': 92}}
    """
    result = engine.screen(request.strategies, request.params)
    
    # 转换响应格式
    strategies_result = {}
    for strategy_id, data in result['strategies'].items():
        strategies_result[strategy_id] = StrategyResult(
            name=data['name'],
            count=data['count'],
            signals=[
                StockSignal(
                    code=s['code'],
                    name=s['name'],
                    reason=s['reason'],
                    metadata=s.get('metadata', {})
                )
                for s in data.get('signals', [])
            ]
        )
    
    return ScreenResponse(
        date=result['date'],
        strategies=strategies_result,
        total=result['total']
    )


@router.get('/kline/{code}')
async def get_kline(code: str, period: str = 'day'):
    """获取 K 线数据"""
    kline = engine.get_kline(code, period)
    if kline is None:
        raise HTTPException(status_code=404, detail='K线数据不存在')
    return kline


@router.get('/quote/{codes}')
async def get_quotes(codes: str):
    """
    获取实时行情
    codes: 逗号分隔的股票代码，如 '600519,000858,300750'
    """
    code_list = codes.split(',')
    quotes = get_quote(code_list)
    
    return [
        QuoteResponse(
            code=q['code'],
            name=q['name'],
            price=q['price'],
            change=q['price'] - q.get('close', q['price']),
            change_pct=q.get('up', 0),
            volume=q.get('volume', 0),
            amount=q.get('amount', 0),
            high=q.get('high', q['price']),
            low=q.get('low', q['price']),
            open=q.get('open', q['price']),
            close=q.get('close', q['price'])
        )
        for q in quotes
    ]


@router.post('/stocks/search', response_model=StockSearchResponse)
async def search_stocks(request: StockSearchRequest):
    """股票搜索：基础筛选 + 模板/公式筛选 + 分页排序"""
    result = engine.search(request.dict())
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])
    template = result.get('applied_template')
    template_resp = None
    if template:
        template_resp = FormulaTemplateResponse(
            id=template['id'],
            strategy_id=template['strategy_id'],
            name=template['name'],
            group_name=template.get('group_name', ''),
            description=template.get('description', ''),
            expression=template.get('expression', ''),
            params_schema=template.get('params_schema', {}),
            tags=template.get('tags', []),
            enabled=bool(template.get('enabled', 1)),
            source=template.get('source', ''),
            created_at=template.get('created_at', ''),
            updated_at=template.get('updated_at', '')
        )

    return StockSearchResponse(
        items=[
            StockSearchItem(
                code=item['code'],
                name=item['name'],
                market=item.get('market', ''),
                industry=item.get('industry', ''),
                concept_tags=item.get('concept_tags', []),
                security_type=item.get('security_type', 'stock'),
                listed_date=item.get('listed_date', ''),
                listed_days=item.get('listed_days', 0),
                price=item.get('price', 0),
                change=item.get('change', 0),
                change_pct=item.get('change_pct', 0),
                volume=item.get('volume', 0),
                amount=item.get('amount', 0),
                total_mv=item.get('total_mv', 0),
                circ_mv=item.get('circ_mv', 0),
                pe_ttm=item.get('pe_ttm'),
                pb=item.get('pb'),
                roe_ttm=item.get('roe_ttm'),
                revenue_yoy_q=item.get('revenue_yoy_q'),
                net_profit_yoy_q=item.get('net_profit_yoy_q'),
                rps50=item.get('rps50'),
                rps120=item.get('rps120'),
                rps250=item.get('rps250'),
                reason=item.get('reason', ''),
                template_id=item.get('template_id'),
                strategy_id=item.get('strategy_id', ''),
            )
            for item in result.get('items', [])
        ],
        total=result.get('total', 0),
        page=result.get('page', request.page),
        page_size=result.get('page_size', request.page_size),
        sort_by=result.get('sort_by', request.sort_by),
        sort_order=result.get('sort_order', request.sort_order),
        applied_formula=result.get('applied_formula', ''),
        applied_template=template_resp,
        date=result.get('date', ''),
        cache_hit=bool(result.get('cache_hit', False)),
    )


@router.post('/stocks/template-results', response_model=StockSearchResponse)
async def get_template_results(request: StockSearchRequest):
    """内置模板预计算结果查询。"""
    if not request.template_id:
        raise HTTPException(status_code=400, detail='缺少模板ID')

    result = engine.get_cached_template_results(request.dict())
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])

    template = result.get('applied_template')
    template_resp = None
    if template:
        template_resp = FormulaTemplateResponse(
            id=template['id'],
            strategy_id=template['strategy_id'],
            name=template['name'],
            group_name=template.get('group_name', ''),
            description=template.get('description', ''),
            expression=template.get('expression', ''),
            params_schema=template.get('params_schema', {}),
            tags=template.get('tags', []),
            enabled=bool(template.get('enabled', 1)),
            source=template.get('source', ''),
            created_at=template.get('created_at', ''),
            updated_at=template.get('updated_at', '')
        )

    return StockSearchResponse(
        items=[
            StockSearchItem(
                code=item['code'],
                name=item['name'],
                market=item.get('market', ''),
                industry=item.get('industry', ''),
                concept_tags=item.get('concept_tags', []),
                security_type=item.get('security_type', 'stock'),
                listed_date=item.get('listed_date', ''),
                listed_days=item.get('listed_days', 0),
                price=item.get('price', 0),
                change=item.get('change', 0),
                change_pct=item.get('change_pct', 0),
                volume=item.get('volume', 0),
                amount=item.get('amount', 0),
                total_mv=item.get('total_mv', 0),
                circ_mv=item.get('circ_mv', 0),
                pe_ttm=item.get('pe_ttm'),
                pb=item.get('pb'),
                roe_ttm=item.get('roe_ttm'),
                revenue_yoy_q=item.get('revenue_yoy_q'),
                net_profit_yoy_q=item.get('net_profit_yoy_q'),
                rps50=item.get('rps50'),
                rps120=item.get('rps120'),
                rps250=item.get('rps250'),
                reason=item.get('reason', ''),
                template_id=item.get('template_id'),
                strategy_id=item.get('strategy_id', ''),
            )
            for item in result.get('items', [])
        ],
        total=result.get('total', 0),
        page=result.get('page', request.page),
        page_size=result.get('page_size', request.page_size),
        sort_by=result.get('sort_by', request.sort_by),
        sort_order=result.get('sort_order', request.sort_order),
        applied_formula=result.get('applied_formula', ''),
        applied_template=template_resp,
        date=result.get('date', ''),
        cache_hit=bool(result.get('cache_hit', False)),
    )


@router.get('/stocks/template-summary', response_model=List[TemplateResultSummary])
async def get_template_summary(date: Optional[str] = None):
    """内置模板预计算结果摘要。"""
    return [
        TemplateResultSummary(
            template_id=item.get('template_id'),
            strategy_id=item.get('strategy_id', ''),
            name=item.get('name', ''),
            description=item.get('description', ''),
            expression=item.get('expression', ''),
            date=item.get('date', ''),
            total=int(item.get('total') or 0),
        )
        for item in get_template_screen_summary(date)
    ]


@router.get('/stocks/{code}', response_model=StockDetailResponse)
async def get_stock_detail(code: str):
    """获取股票详情"""
    result = engine.get_stock_detail(code)
    if not result:
        raise HTTPException(status_code=404, detail='股票不存在')

    return StockDetailResponse(
        basic=StockDetailBasic(**result.get('basic', {})),
        quote=StockDetailQuote(**result.get('quote', {})),
        fundamentals=StockDetailFundamentals(**result.get('fundamentals', {})),
        technicals=StockDetailTechnicals(**result.get('technicals', {})),
        kline_summary=StockDetailKLineSummary(**result.get('kline_summary', {})),
        template_hits=[
            StockTemplateHit(**hit)
            for hit in result.get('template_hits', [])
        ],
        applied_date=result.get('applied_date', ''),
    )
