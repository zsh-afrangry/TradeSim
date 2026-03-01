from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.v1 import simulate, records, ai
from app.db.session import engine
from app.db.models import Base
from app.core.config import settings
import os

# 自动创建必要的数据目录与数据库表结构
os.makedirs(settings.LOCAL_LOGS_DIR, exist_ok=True)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TradeSim API",
    description="基于 Python + Polars 的高性能股票交易回测系统",
    version="1.0.0"
)

# 配置 CORS，允许前端 Vue3 跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册子路由
app.include_router(simulate.router, prefix="/api/v1/simulate", tags=["回测引擎"])
app.include_router(records.router, prefix="/api/v1/records", tags=["回测记录"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI研判引擎"])


# ── standalone 模式：挂载前端静态资源，由后端统一伺服 ──────────────────
# development 模式下前端由 Vite 独立服务（端口 5173），此块不生效
if settings.is_standalone:
    # __file__ 在打包后指向 _internal/ 内的 main.pyc，static 就在同级目录
    _static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    print(f"[TradeSim] standalone 模式，静态文件目录: {_static_dir}")
    print(f"[TradeSim] 静态目录存在: {os.path.exists(_static_dir)}")

    if os.path.exists(_static_dir):
        # 将整个 static/ 目录挂载为 /static，应对 Vite 构建产物中的各种子目录
        app.mount("/static", StaticFiles(directory=_static_dir), name="static_root")

        # 单独挂载 assets/ 以支持 Vite 默认的 /assets 路径
        _assets_dir = os.path.join(_static_dir, "assets")
        if os.path.exists(_assets_dir):
            app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")
            print(f"[TradeSim] 已挂载 /assets 路径")

        @app.get("/")
        async def serve_index():
            """根路径直接返回 Vue 编译后的 index.html"""
            return FileResponse(os.path.join(_static_dir, "index.html"))

        @app.get("/{catchall:path}")
        async def serve_vue_app(catchall: str):
            """所有未匹配 API 的路径都回落到 index.html，供 Vue Router 处理"""
            file_path = os.path.join(_static_dir, catchall)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(_static_dir, "index.html"))
    else:
        print(f"[TradeSim] 警告：static 目录不存在，前端压根没有被打包进来")

        @app.get("/")
        async def root_fallback():
            return {"message": "static 目录未找到，请检查打包是否包含前端资源。", "static_path": _static_dir}

else:
    # development 模式：根路径只返回后端状态，前端由 Vite 独立服务
    @app.get("/")
    async def root():
        return {"message": "TradeSim Backend is running. Frontend served by Vite on port 5173."}


# 可以通过命令启动: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
