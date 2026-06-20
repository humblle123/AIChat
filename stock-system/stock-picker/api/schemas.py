"""API 数据模型"""
from pydantic import BaseModel
from typing import List, Dict, Optional, Any


class FormulaResponse(BaseModel):
    """公式响应模型"""
    id: int
    name: str
    description: str = ''
    code: str = ''
    params: Dict[str, Any] = {}
    is_active: bool = True
    created_at: str = ''
    updated_at: str = ''


class FormulaTemplateResponse(BaseModel):
    """内置策略模板响应"""
    id: int
    strategy_id: str
    name: str
    group_name: str = ''
    description: str = ''
    expression: str = ''
    params_schema: Dict[str, Any] = {}
    tags: List[str] = []
    enabled: bool = True
    source: str = ''
    created_at: str = ''
    updated_at: str = ''


class StockSearchFilters(BaseModel):
    """股票搜索筛选条件"""
    min_total_mv: Optional[float] = None
    max_total_mv: Optional[float] = None
    min_circ_mv: Optional[float] = None
    max_circ_mv: Optional[float] = None
    min_listed_days: Optional[int] = None
    max_listed_days: Optional[int] = None
    min_change_pct: Optional[float] = None
    max_change_pct: Optional[float] = None
    min_pe_ttm: Optional[float] = None
    max_pe_ttm: Optional[float] = None
    min_pb: Optional[float] = None
    max_pb: Optional[float] = None
    min_roe_ttm: Optional[float] = None
    max_roe_ttm: Optional[float] = None
    min_revenue_yoy_q: Optional[float] = None
    max_revenue_yoy_q: Optional[float] = None
    min_net_profit_yoy_q: Optional[float] = None
    max_net_profit_yoy_q: Optional[float] = None
    min_rps50: Optional[float] = None
    min_rps120: Optional[float] = None
    min_rps250: Optional[float] = None
    include_st: bool = False
    exclude_suspended: bool = True


class StockSearchRequest(BaseModel):
    """股票搜索请求"""
    markets: List[str] = []
    industries: List[str] = []
    concepts: List[str] = []
    keyword: str = ''
    filters: StockSearchFilters = StockSearchFilters()
    formula: str = ''
    template_id: Optional[int] = None
    template_params: Dict[str, Any] = {}
    sort_by: str = 'change_pct'
    sort_order: str = 'desc'
    page: int = 1
    page_size: int = 20


class StockSearchItem(BaseModel):
    """股票搜索结果项"""
    code: str
    name: str
    market: str = ''
    industry: str = ''
    concept_tags: List[str] = []
    security_type: str = 'stock'
    listed_date: str = ''
    listed_days: int = 0
    price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    amount: float = 0.0
    total_mv: float = 0.0
    circ_mv: float = 0.0
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    roe_ttm: Optional[float] = None
    revenue_yoy_q: Optional[float] = None
    net_profit_yoy_q: Optional[float] = None
    rps50: Optional[float] = None
    rps120: Optional[float] = None
    rps250: Optional[float] = None
    reason: str = ''
    template_id: Optional[int] = None
    strategy_id: str = ''


class StockSearchResponse(BaseModel):
    """股票搜索响应"""
    items: List[StockSearchItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    sort_by: str = 'change_pct'
    sort_order: str = 'desc'
    applied_formula: str = ''
    applied_template: Optional[FormulaTemplateResponse] = None
    date: str = ''
    cache_hit: bool = False


class TemplateResultSummary(BaseModel):
    """内置模板缓存摘要"""
    template_id: int
    strategy_id: str
    name: str = ''
    description: str = ''
    expression: str = ''
    date: str = ''
    total: int = 0


class StockDetailBasic(BaseModel):
    """股票基础信息"""
    code: str
    name: str = ''
    market: str = ''
    industry: str = ''
    concept_tags: List[str] = []
    security_type: str = 'stock'
    listed_date: str = ''
    listed_days: int = 0
    is_delisted: bool = False
    is_st: bool = False
    is_suspended: bool = False


class StockDetailQuote(BaseModel):
    """股票行情信息"""
    trade_date: str = ''
    price: float = 0.0
    prev_close: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    amount: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    pe: Optional[float] = None
    pb: Optional[float] = None
    total_mv: Optional[float] = None
    circ_mv: Optional[float] = None


class StockDetailFundamentals(BaseModel):
    """股票基本面信息"""
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    roe_ttm: Optional[float] = None
    revenue_yoy_q: Optional[float] = None
    net_profit_yoy_q: Optional[float] = None
    debt_ratio: Optional[float] = None
    report_period: str = ''


class StockDetailTechnicals(BaseModel):
    """股票技术指标"""
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    ma250: Optional[float] = None
    rsi14: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    macd_hist: Optional[float] = None
    volume_ratio_1d: Optional[float] = None
    avg_volume_5d: Optional[float] = None
    kdj_k: Optional[float] = None
    kdj_d: Optional[float] = None
    kdj_j: Optional[float] = None
    rps50: Optional[float] = None
    rps120: Optional[float] = None
    rps250: Optional[float] = None


class StockDetailKLineSummary(BaseModel):
    """K线摘要"""
    last_trade_date: str = ''
    last_close: float = 0.0
    highest_250d: Optional[float] = None
    lowest_250d: Optional[float] = None
    day_count: int = 0


class StockTemplateHit(BaseModel):
    """命中的模板"""
    template_id: int
    strategy_id: str
    name: str
    group_name: str = ''
    reason: str = ''
    matched: bool = True
    params: Dict[str, Any] = {}


class StockDetailResponse(BaseModel):
    """股票详情响应"""
    basic: StockDetailBasic
    quote: StockDetailQuote
    fundamentals: StockDetailFundamentals
    technicals: StockDetailTechnicals
    kline_summary: StockDetailKLineSummary
    template_hits: List[StockTemplateHit] = []
    applied_date: str = ''


class FormulaCreate(BaseModel):
    """创建公式请求"""
    name: str
    description: str = ''
    code: str = ''
    params: Dict[str, Any] = {}


class FormulaUpdate(BaseModel):
    """更新公式请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class ScreenResultResponse(BaseModel):
    """选股结果响应"""
    id: int
    date: str
    formula_id: int
    formula_name: str = ''
    code: str
    name: str = ''
    reason: str = ''
    metadata: Dict[str, Any] = {}


class StockSignal(BaseModel):
    """股票信号"""
    code: str
    name: str
    reason: str = ''
    metadata: Dict[str, Any] = {}


class StrategyResult(BaseModel):
    """策略选股结果"""
    name: str
    count: int
    signals: List[StockSignal] = []


class ScreenResponse(BaseModel):
    """选股响应"""
    date: str
    strategies: Dict[str, StrategyResult] = {}
    total: int = 0


class KLineResponse(BaseModel):
    """K线数据响应"""
    code: str
    name: str
    period: str
    data: List[Dict[str, Any]] = []


class QuoteResponse(BaseModel):
    """行情数据响应"""
    code: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    amount: float
    high: float
    low: float
    open: float
    close: float


class StrategyInfo(BaseModel):
    """策略信息"""
    id: str
    name: str
    description: str
    group: str = ''
    template_count: int = 0
    templates: List[FormulaTemplateResponse] = []
    params: Dict[str, Any] = {}


class ScreenRequest(BaseModel):
    """选股请求"""
    strategies: List[str]
    params: Dict[str, Dict[str, Any]] = {}


class FormulaValidateRequest(BaseModel):
    """公式校验请求"""
    formula: str = ''
    template_id: Optional[int] = None
    template_params: Dict[str, Any] = {}


class FormulaValidateResponse(BaseModel):
    """公式校验响应"""
    valid: bool
    errors: List[str] = []
    used_fields: List[str] = []
    normalized_formula: str = ''


# ====== OpenAPI 元数据 ======

API_TAGS_METADATA = [
    {'name': 'templates', 'description': '内置公式模板(b1/s2/s3/kd1)与公式校验。'},
    {'name': 'search', 'description': '股票搜索 / 模板结果 / 摘要。'},
    {'name': 'detail', 'description': '股票详情与 K 线。'},
    {'name': 'health', 'description': '健康检查与 K8s 探针。'},
]
