from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db, mongo_collection
from app.db.models import SimulationRecord
from app.schemas.record import SaveRecordRequest, RecordBriefResponse, RecordDetailResponse
from app.core.config import settings
from typing import List
from datetime import datetime
import logging
import json
import os
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# 本地 JSON 文件存取工具函数（standalone 模式专用）
# ══════════════════════════════════════════════════════════════════════════════

def _local_log_path(log_id: str) -> str:
    """返回本地 JSON 日志文件的绝对路径"""
    os.makedirs(settings.LOCAL_LOGS_DIR, exist_ok=True)
    return os.path.join(settings.LOCAL_LOGS_DIR, f"{log_id}.json")

def _write_local_log(data: dict) -> str:
    """将回测大数组写入本地 JSON 文件，返回文件 UUID（充当 mongo_id 的替代）"""
    log_id = str(uuid.uuid4())
    with open(_local_log_path(log_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return log_id

def _read_local_log(log_id: str) -> dict:
    """从本地 JSON 文件中读取回测大数组，找不到时返回 None"""
    path = _local_log_path(log_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════
# 路由实现
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/save-favorite", summary="持久化并收藏该次成功的组合与参数", response_model=dict)
async def save_record(payload: SaveRecordRequest, db: Session = Depends(get_db)):
    """
    双模式存储：
      - development : 大数组 → MongoDB，索引 → MySQL
      - standalone  : 大数组 → 本地 JSON 文件，索引 → SQLite
    """
    logger.info(f"开启存证写入: {payload.request.symbol} | 模式: {settings.APP_MODE}")

    try:
        large_doc = {
            "equity_curve": [item.model_dump() for item in payload.response.equity_curve],
            "execution_records": [item.model_dump() for item in payload.response.execution_records],
            "saved_at_node": datetime.now().isoformat()
        }

        # ── 第 1 步：大数组落盘 ────────────────────────────────
        if settings.is_standalone:
            log_id = _write_local_log(large_doc)
        else:
            from bson import ObjectId
            mongo_res = await mongo_collection.insert_one(large_doc)
            log_id = str(mongo_res.inserted_id)

        # ── 第 2 步：索引落库（SQLite or MySQL，SQLAlchemy 屏蔽差异）─
        db_record = SimulationRecord(
            mongo_log_id=log_id,
            strategy_name=payload.request.strategy_name,
            symbol=payload.request.symbol,
            start_date=payload.request.start_date,
            end_date=payload.request.end_date,
            data_frequency=payload.request.data_frequency,
            strategy_params=payload.request.strategy_params,
            total_return=payload.response.metrics.total_return,
            annualized_return=payload.response.metrics.annualized_return,
            max_drawdown=payload.response.metrics.max_drawdown,
            win_rate=payload.response.metrics.win_rate,
            total_trades=payload.response.metrics.total_trades
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)

        logger.info(f"存证成功! ID:{db_record.id} | log_id:{log_id}")
        return {"message": "存证成功！", "record_id": db_record.id, "log_id": log_id}

    except Exception as e:
        db.rollback()
        logger.error(f"存证失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="存储层写入异常")


@router.get("/list", summary="查阅所有已收藏的回测（极速返回轻对象）", response_model=List[RecordBriefResponse])
def get_favorites(db: Session = Depends(get_db)):
    """列表查询只访问轻量级关系型库，两种模式均秒级响应"""
    records = db.query(SimulationRecord).order_by(SimulationRecord.total_return.desc()).limit(100).all()
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
    双模式详情读取：
      - development : 通过 mongo_log_id 去 MongoDB 查大 JSON
      - standalone  : 通过 log_id 读取本地 JSON 文件
    """
    r = db.query(SimulationRecord).filter(SimulationRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="未找到该回测记录")
    if not r.mongo_log_id:
        raise HTTPException(status_code=500, detail="数据撕裂，详情凭证已遗失")

    # ── 读取大数组 ────────────────────────────────────────────
    if settings.is_standalone:
        log_doc = _read_local_log(r.mongo_log_id)
        if not log_doc:
            raise HTTPException(status_code=404, detail="本地日志文件不存在或已被清理")
    else:
        from bson import ObjectId
        try:
            log_doc = await mongo_collection.find_one({"_id": ObjectId(r.mongo_log_id)})
        except Exception as e:
            logger.error(f"MongoDB 读取失败: {e}")
            raise HTTPException(status_code=500, detail="从 MongoDB 读取详情失败")
        if not log_doc:
            raise HTTPException(status_code=404, detail="MongoDB 大对象已被清理或不存在")

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
        start_date=r.start_date.strftime("%Y-%m-%d"),
        end_date=r.end_date.strftime("%Y-%m-%d"),
        strategy_params=r.strategy_params or {},
        equity_curve=log_doc.get("equity_curve", []),
        execution_records=log_doc.get("execution_records", [])
    )
