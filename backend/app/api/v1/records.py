from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db, mongo_collection
from app.db.models import SimulationRecord
from app.schemas.record import SaveRecordRequest, RecordBriefResponse, RecordDetailResponse
from typing import List
from datetime import datetime
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/save-favorite", summary="持久化并收藏该次成功的组合与参数", response_model=dict)
async def save_record(payload: SaveRecordRequest, db: Session = Depends(get_db)):
    """
    分离架构重头戏:
    前端丢过来巨大的 JSON (含配置对象与结果大对象数组)。
    我们将大数组发落至 MongoDB 享受高性能，将搜索字典下发给 MySQL。
    """
    logger.info(f"开启双库转存: {payload.request.symbol}")
    
    try:
        # ----- 第 1 步: 温冷集群转存 (MongoDB) -----
        # 仅将沉重、复杂、且无需排序比对的回撤曲线和流水扔进去
        mongo_doc = {
            "equity_curve": [item.model_dump() for item in payload.response.equity_curve],
            "execution_records": [item.model_dump() for item in payload.response.execution_records],
            "saved_at_node": datetime.now().isoformat()
        }
        # 异步驱动插表, 获取 MongoDB 原生 ObjectID (作为纽带)
        mongo_res = await mongo_collection.insert_one(mongo_doc)
        mongo_id_str = str(mongo_res.inserted_id)
        
        # ----- 第 2 步: 主干索引表转存 (MySQL) -----
        db_record = SimulationRecord(
            mongo_log_id=mongo_id_str, # 捆绑的 MongoDB 主键（外键关联思想）
            strategy_name=payload.request.strategy_name,
            symbol=payload.request.symbol,
            start_date=payload.request.start_date,
            end_date=payload.request.end_date,
            data_frequency=payload.request.data_frequency,
            strategy_params=payload.request.strategy_params,
            # 将 metrics 指标转存作为强类型数值，以便后续 ORDER BY total_return DESC
            total_return=payload.response.metrics.total_return,
            annualized_return=payload.response.metrics.annualized_return,
            max_drawdown=payload.response.metrics.max_drawdown,
            win_rate=payload.response.metrics.win_rate,
            total_trades=payload.response.metrics.total_trades
        )
        
        db.add(db_record)
        # SQLAlchemy 事务提交，保障 ACID
        db.commit()
        db.refresh(db_record)
        
        logger.info(f"收藏成功! MySQL ID:{db_record.id} 绑定 MongoDB ObjectID: {mongo_id_str}")
        return {"message": "双端落库存证成功！", "record_id": db_record.id, "mongo_log_id": mongo_id_str}
        
    except Exception as e:
        # 万一崩溃，SQL这边就不要存脏数据了
        db.rollback()
        logger.error(f"存证失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="网络或数据库层出现双写异常")

@router.get("/list", summary="查阅所有已收藏的回测（极速返回轻对象）", response_model=List[RecordBriefResponse])
def get_favorites(db: Session = Depends(get_db)):
    """
    查阅时只需访问 MySQL 从而秒级拿列表排序，而无需等待 MongoDB 那十万个节点解析
    """
    records = db.query(SimulationRecord).order_by(SimulationRecord.total_return.desc()).limit(100).all()
    
    # 转换为简化的外向对象格式
    results = []
    for r in records:
        results.append(RecordBriefResponse(
            id=r.id,
            symbol=r.symbol,
            strategy_name=r.strategy_name,
            total_return=float(r.total_return),
            max_drawdown=float(r.max_drawdown),
            win_rate=float(r.win_rate),
            total_trades=r.total_trades,
            created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            data_frequency=getattr(r, "data_frequency", "daily") or "daily"
        ))
    return results

@router.get("/detail/{record_id}", summary="联表查询某次跑分详情图表数据", response_model=RecordDetailResponse)
async def get_record_detail(record_id: int, db: Session = Depends(get_db)):
    """
    通过 MySQL 的轻量化主键，查询全量的参数。
    更重要的是，通过跨表的 mongo_log_id 去冷库里揪出那极其庞大的曲线数据。
    """
    r = db.query(SimulationRecord).filter(SimulationRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="未在一级库内找到该测试记录")
        
    if not r.mongo_log_id:
        raise HTTPException(status_code=500, detail="数据撕裂，关联的 MongoDB 凭证已遗失")

    # ----- 转去 MongoDB 查大 JSON -----
    logger.info(f"读取流水全貌：ObjectId({r.mongo_log_id})")
    try:
        mongo_doc = await mongo_collection.find_one({"_id": ObjectId(r.mongo_log_id)})
    except Exception as e:
        logger.error(f"MongoDB 解析主键崩坏: {e}")
        raise HTTPException(status_code=500, detail="从非关系型冷库中取回失败")
        
    if not mongo_doc:
        raise HTTPException(status_code=404, detail="冷库大对象已被清理或不存在")

    # 收拢归一返回前端
    return RecordDetailResponse(
        id=r.id,
        symbol=r.symbol,
        strategy_name=r.strategy_name,
        total_return=float(r.total_return),
        max_drawdown=float(r.max_drawdown),
        win_rate=float(r.win_rate),
        total_trades=r.total_trades,
        created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        data_frequency=getattr(r, "data_frequency", "daily") or "daily",
        # 新增扩展查询的参数
        start_date=r.start_date.strftime("%Y-%m-%d"),
        end_date=r.end_date.strftime("%Y-%m-%d"),
        strategy_params=r.strategy_params or {},
        # 新增 Mongo 中取回的大型数组 (去掉 mongo 生成自带的 _id 因为前端无法序列化)
        equity_curve=mongo_doc.get("equity_curve", []),
        execution_records=mongo_doc.get("execution_records", [])
    )
