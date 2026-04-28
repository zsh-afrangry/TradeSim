from fastapi import APIRouter, HTTPException
from app.schemas.simulate import SimulationRequest, SimulationResponse, SimulationMetrics, EquitySnapshot, TradeRecord
from app.services.data_fetcher import DataFetcher
from app.strategy.specific.grid_trade import GridTradingStrategy
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/run", response_model=SimulationResponse, summary="执行回测策略并返回分析结果")
async def run_simulation(request: SimulationRequest):
    """
    接收前端同步调用，按约定规范和指定策略名字启动 Polars 引擎。
    """
    logger.info(f"开启回测执行 - 代码:{request.symbol}, 策略:{request.strategy_name}")

    # 1. 数据准备环节：通过 AkShare -> Polars，全面支持分钟线切片拉取
    df_pl = DataFetcher.fetch_a_share_data(
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        frequency=request.data_frequency,
        adjust="qfq"
    )

    if df_pl is None or df_pl.is_empty():
        raise HTTPException(status_code=400, detail=f"无法获取代码 {request.symbol} 在指定日期范围内的数据")

    # 2. 策略路由：基于 strategy_name 进行动态分发
    # （未来可以改造成工厂模式或者注册映射机制，这里暂举一例网格）
    try:
        if request.strategy_name == "GRID_TRADING":
            engine = GridTradingStrategy(
                df=df_pl,
                params=request.strategy_params,
                initial_capital=request.initial_capital,
                commission_rate=request.commission_rate,
                slippage=request.slippage
            )
        else:
            raise HTTPException(status_code=400, detail=f"未找到该策略类 {request.strategy_name}, 敬请期待")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. 执行核心循环计算
    try:
        raw_results = engine.execute()
    except Exception as e:
        logger.error(f"测算引擎意外崩溃：{e}")
        raise HTTPException(status_code=500, detail="执行量化模型时遇到严重错误")

    # 4. 组装契约 Pydantic 以返还
    return SimulationResponse(
        metrics=SimulationMetrics(**raw_results["metrics"]),
        equity_curve=[EquitySnapshot(**entry) for entry in raw_results["equity_curve"]],
        execution_records=[TradeRecord(**log) for log in raw_results["execution_records"]]
    )
