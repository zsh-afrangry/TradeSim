import os
import sys
from dotenv import load_dotenv

# PyInstaller 打包后 __file__ 指向 _internal/ 内的路径
# load_dotenv() 必须显式指向 .env 所在目录，否则打包后找不到 .env
_base_dir = os.path.dirname(os.path.abspath(__file__))
# config.py 位于 app/core/config.py，.env 在 backend/ 根目录（打包后同在 _internal/）
_env_path = os.path.join(_base_dir, "..", "..", ".env")
load_dotenv(dotenv_path=_env_path)

class Settings:
    # ── 运行模式配置 ──────────────────────────────────────────
    # development : 联机开发，使用 MySQL + MongoDB
    # standalone  : 本地打包交付，使用 SQLite + 本地 JSON 文件
    APP_MODE: str = os.getenv("APP_MODE", "development")

    # ── MySQL 配置（仅 development 模式生效）─────────────────
    MYSQL_URL: str = os.getenv("MYSQL_URL", "mysql+pymysql://root:root@127.0.0.1:3306/tradesim")

    # ── MongoDB 配置（仅 development 模式生效）────────────────
    MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME: str = "tradesim"
    MONGO_COLLECTION_LOGS: str = "simulation_logs"

    # ── 本地单机存储配置（仅 standalone 模式生效）─────────────
    SQLITE_URL: str = "sqlite:///./data/tradesim.db"
    LOCAL_LOGS_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "logs")

    # ── AI 接口配置（两种模式均生效）─────────────────────────
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-max")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    @property
    def effective_db_url(self) -> str:
        """根据运行模式返回实际生效的数据库连接串"""
        if self.APP_MODE == "standalone":
            return self.SQLITE_URL
        return self.MYSQL_URL

    @property
    def is_standalone(self) -> bool:
        return self.APP_MODE == "standalone"

settings = Settings()
