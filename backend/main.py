from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import simulate, records, ai

app = FastAPI(
    title="TradeSim API",
    description="基于 Python + Polars 的高性能股票交易回测系统",
    version="1.0.0"
)

# 配置 CORS，允许前端 Vue3 跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应替换为实际的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册子路由
app.include_router(simulate.router, prefix="/api/v1/simulate", tags=["回测引擎"])
app.include_router(records.router, prefix="/api/v1/records", tags=["回测记录"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI研判引擎"])

@app.get("/")
async def root():
    return {"message": "Welcome to TradeSim Backend Service!"}

# 可以通过命令启动: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
