from pydantic import BaseModel
from typing import Dict, Any, List
from app.schemas.simulate import SimulationRequest, SimulationResponse

class SaveRecordRequest(BaseModel):
    """
    保存记录时的入参。
    它巧妙地包含了当初用户调用的配置参数（request）以及我们算出来的结果参数（response）。
    将两块打包发给后端进行 MySQL 和 MongoDB 存证。
    """
    request: SimulationRequest
    response: SimulationResponse

class RecordBriefResponse(BaseModel):
    """返回给前端的列表页轻数据对象 (不用渲染曲线图)"""
    id: int
    symbol: str
    strategy_name: str
    total_return: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    created_at: str
    data_frequency: str = "daily"

    class Config:
        from_attributes = True  # 允许读取 SQLAlchemy 对象属性

class RecordDetailResponse(RecordBriefResponse):
    """
    返回给详情页的全量数据结构
    继承了 Brief 中的所有指标，外加 MongoDB 中的深层数组
    """
    start_date: str
    end_date: str
    strategy_params: Dict[str, Any]
    
    # 以下是从 MongoDB 取回的
    equity_curve: List[Dict[str, Any]]
    execution_records: List[Dict[str, Any]]
