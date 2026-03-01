@echo off
chcp 65001
echo =========================================
echo 开始打包 TradeSim 单机免安装版...
echo =========================================

echo 0. 切换到正确的 Conda 环境变量 (tradesim)
call conda activate tradesim

echo 1. 安装 PyInstaller 打包工具
pip install pyinstaller

echo 2. 清理旧的打包文件
rmdir /s /q build
rmdir /s /q dist
del /q *.spec

echo 2.5 编译前端 Vue 项目
cd ..\frontend
call npm install
call npm run build

echo 2.6 拷贝前端静态文件到后端
cd ..\backend
rmdir /s /q static
mkdir static
xcopy /e /i /y ..\frontend\dist static\

echo 3. 注入 APP_MODE=standalone（仅在打包期间临时覆写 .env）
copy .env .env.dev.bak > nul
echo APP_MODE=standalone >> .env

echo 3.5 开始执行黑魔法打包 (耗时可能较长，请耐心等待...)
pyinstaller --noconfirm --name "TradeSim回测引擎" ^
--add-data "static;static" ^
--add-data ".env;." ^
--collect-data "akshare" ^
--copy-metadata "curl_cffi" ^
--hidden-import="uvicorn.logging" ^
--hidden-import="uvicorn.loops" ^
--hidden-import="uvicorn.loops.auto" ^
--hidden-import="uvicorn.protocols" ^
--hidden-import="uvicorn.protocols.http" ^
--hidden-import="uvicorn.protocols.http.auto" ^
--hidden-import="uvicorn.protocols.websockets" ^
--hidden-import="uvicorn.protocols.websockets.auto" ^
--hidden-import="uvicorn.lifespan" ^
--hidden-import="uvicorn.lifespan.on" ^
--hidden-import="uvicorn.lifespan.off" ^
--hidden-import="polars" ^
--hidden-import="akshare" ^
--onedir run_app.py

echo 4. 恢复开发用的 .env
copy .env.dev.bak .env > nul
del .env.dev.bak > nul 2>&1

echo.
echo =========================================
echo 打包完成！请进入 backend\dist\TradeSim回测引擎\ 双击【TradeSim回测引擎.exe】进行测试。
echo =========================================
pause
