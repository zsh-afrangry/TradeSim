from pydantic import BaseModel, Field
from typing import Dict, Any, List

class SimulationRequest(BaseModel):
    symbol: str = Field(..., description="股票代码,如 000400", examples=["000400"])
    start_date: str = Field(..., description="回测起始日期, YYYY-MM-DD", examples=["2024-01-01"])
    end_date: str = Field(..., description="回测结束日期, YYYY-MM-DD", examples=["2024-12-31"])
    data_frequency: str = Field("daily", description="数据切片频率: daily, 5min, 1min")
    initial_capital: float = Field(100000.0, description="初始本金")
    commission_rate: float = Field(default=0.00025, description="交易佣金费率")
    slippage: float = Field(default=0.01, description="滑点设置，模拟价格偏差")
    
    strategy_name: str = Field(..., description="策略路由标识", examples=["GRID_TRADING"])
    strategy_params: Dict[str, Any] = Field(
        default_factory=dict, 
        description="策略扩展参数字典，透传给具体算法",
        examples=[{"lower_bound": 20.0, "upper_bound": 30.0, "grid_step_pct": 5.0, "base_position_ratio": 0.5, "funds_per_grid": 10000.0}]
    )

class EquitySnapshot(BaseModel):
    date: str
    close_price: float
    net_value: float
    benchmark_value: float  # 基础基准线的拟合收益
    position_utilization: float # 仓位使用占比 0~1
    drawdown: float

class TradeRecord(BaseModel):
    timestamp: str
    action: str  # BUY / SELL
    price: float
    volume: float
    amount: float
    commission: float
    slippage_cost: float

class SimulationMetrics(BaseModel):
    total_return: float
    annualized_return: float
    max_drawdown: float
    win_rate: float
    total_trades: int

class SimulationResponse(BaseModel):
    metrics: SimulationMetrics
    equity_curve: List[EquitySnapshot]
    execution_records: List[TradeRecord]
