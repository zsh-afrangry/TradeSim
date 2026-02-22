from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# 1. 初始化 MySQL 引擎和 Session（用于存储关系型查询的主数据）
engine = create_engine(
    settings.MYSQL_URL,
    pool_pre_ping=True,  # 开启断线自动重连侦测
    pool_recycle=3600    # 避免数据库主动断开长时间不活动的连接
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. 初始化 MongoDB 异步引擎（用于存储不参与查询计算的大体积 JSON 数组）
mongo_client = AsyncIOMotorClient(settings.MONGO_URL)
mongo_db = mongo_client[settings.MONGO_DB_NAME]
mongo_collection = mongo_db[settings.MONGO_COLLECTION_LOGS]
