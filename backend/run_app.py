import uvicorn
import webbrowser
import threading
import time
from main import app  # 引入 FastAPI 实例

# 浏览器打开的目标地址（standalone 模式下根路径直接返回前端 index.html）
_APP_URL = "http://127.0.0.1:8000"

def open_browser():
    # 等待 3 秒，确保 uvicorn 完全启动、静态文件路由全部注册完毕
    time.sleep(3)
    print(f"\n✅ TradeSim 已就绪，正在为您打开前端界面: {_APP_URL}")
    webbrowser.open(_APP_URL)

if __name__ == "__main__":
    print("🚀 TradeSim 回测引擎正在启动，请稍候...")
    print(f"   前端界面将在浏览器中自动打开: {_APP_URL}")

    # 开一个后台线程去启动浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    # 在主线程启动 FastAPI 后端服务
    # 注意：打包 exe 时不能用 reload=True
    uvicorn.run(app, host="127.0.0.1", port=8000)
