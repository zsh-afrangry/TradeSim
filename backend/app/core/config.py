import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # MySQL 关系型数据库配置
    MYSQL_URL = os.getenv("MYSQL_URL", "mysql+pymysql://root:root@127.0.0.1:3306/tradesim")
    
    # MongoDB 非关系型大数组存储配置
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME = "tradesim"
    MONGO_COLLECTION_LOGS = "simulation_logs"
    
    # AI 接口配置
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen-max")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

settings = Settings()
