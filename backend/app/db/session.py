from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import os

# ── 关系型数据库引擎 ──────────────────────────────────────────────────────────
# development 模式: 连接 MySQL（需要本地 MySQL 服务在运行）
# standalone  模式: 连接 SQLite（自动在 data/ 目录生成 .db 文件，无需安装任何服务）
_connect_args = {"check_same_thread": False} if settings.is_standalone else {}

engine = create_engine(
    settings.effective_db_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── 非关系型存储（仅 development 模式挂载 MongoDB）────────────────────────────
if not settings.is_standalone:
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_client = AsyncIOMotorClient(settings.MONGO_URL)
    mongo_db     = mongo_client[settings.MONGO_DB_NAME]
    mongo_collection = mongo_db[settings.MONGO_COLLECTION_LOGS]
else:
    # standalone 模式下，mongo_collection 不会被调用，置为 None 即可
    mongo_client     = None
    mongo_db         = None
    mongo_collection = None
