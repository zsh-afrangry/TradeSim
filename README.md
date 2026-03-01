# TradeSim 回测引擎 - 开发与打包指南

## 1. 忽略文件与编译产物约定

在日常开发阶段中，项目会产生部分编译产物及运行缓存。以下文件与目录已加入 `.gitignore`，**一律不纳入版本管理**：

| 路径 | 说明 |
|---|---|
| `backend/dist/` | PyInstaller 打包输出目录 |
| `backend/build/` | PyInstaller 中间编译产物 |
| `backend/static/` | 从前端 `dist/` 拷贝的静态资源（每次打包重新生成） |
| `backend/*.spec` | PyInstaller 自动生成的打包配置文件 |
| `**/__pycache__/` | Python 字节码缓存 |
| `backend/.env` | 敏感配置（API Key 等），严禁签入 Git |

---

## 2. 分支管理策略

**使用单一 `main` 分支，`feature/standalone-build` 已退休。**

过去项目曾维护两套代码（开发分支 vs. 打包分支），导致每次新功能上线后都需要手动向打包分支同步，随时间推移合并成本极高。

现在的策略是：**一套代码，用配置驱动两种运行模式。**

```
main ─────── 开发迭代 ─────── 开发迭代 ─────── 开发迭代
                │                   │
           build.bat            build.bat
                │                   │
          dist/v1.0.exe       dist/v2.0.exe   ← 永远从 main 打出
```

`feature/standalone-build` 分支保留作为历史记录，**不再向其提交任何代码**。

---

## 3. 运行模式（APP_MODE）配置开关

这是整个架构的核心设计。通过 `backend/.env` 中的一个字段，控制程序的完整运行行为：

```dotenv
APP_MODE=development   # 联机开发（默认值）
APP_MODE=standalone    # 本地打包交付
```

### 两种模式的完整对比

| 维度 | `development` 开发模式 | `standalone` 单机模式 |
|---|---|---|
| **关系型存储** | MySQL（需本地服务） | SQLite（自动创建 `data/tradesim.db`） |
| **非关系型存储** | MongoDB（需本地服务） | 本地 JSON 文件（`data/logs/*.json`） |
| **启动方式** | `uvicorn main:app --reload` | 双击 `TradeSim回测引擎.exe` |
| **前端服务** | Vite 独立开发服务器（端口 5173） | 由 FastAPI 托管编译后静态资源（端口 8000） |
| **目标用户** | 开发者本人 | 甲方最终用户 |

### 代码层响应逻辑

配置开关驱动了以下三个文件的运行时行为分叉，**其余所有业务代码（策略引擎、数据拉取等）完全不感知模式差异**：

```
backend/app/core/config.py   → 提供 settings.is_standalone 属性
backend/app/db/session.py    → 按模式选择 SQLAlchemy 引擎 / 是否挂载 Motor
backend/app/api/v1/records.py → 按模式选择 MongoDB 或本地 JSON 文件读写
```

---

## 4. 如何执行本地打包（一键流程）

打包过程**无需手动修改任何代码**，`build.bat` 会自动处理所有模式切换：

```bash
# 在 backend/ 目录下运行
.\build.bat
```

`build.bat` 的执行顺序：
1. 编译前端 Vue 项目（`npm run build`）
2. 将前端 `dist/` 拷贝至 `backend/static/`
3. **临时**在 `.env` 末尾追加 `APP_MODE=standalone`（不动原始配置）
4. 执行 PyInstaller 打包
5. **自动还原** `.env` 至开发状态（`APP_MODE=development`）

> **打包完成后，`.env` 会自动还原，你的本地开发环境不受任何影响。**

输出物位于 `backend/dist/TradeSim回测引擎/`，双击 `TradeSim回测引擎.exe` 即可启动。

---

## 5. 本地开发环境启动

```bash
# 启动后端（联机开发模式，确保 MySQL 和 MongoDB 在运行）
cd backend
uvicorn main:app --reload

# 启动前端（独立开发服务器，代理至后端 8000 端口）
cd frontend
npm run dev
```

---

## 6. 关键依赖说明

- **`motor`**：仅在 `development` 模式下被加载，`standalone` 模式下不会导入，避免打包体积膨胀。
- **`bson`**：随 `motor` 按需导入，`standalone` 模式无需安装。
- **`akshare`**：两种模式均需要，打包时通过 `--collect-data akshare` 确保内置 JSON 数据文件随包携带。
- **`curl_cffi`**：`akshare` 的内部依赖，打包时通过 `--copy-metadata curl_cffi` 确保元数据随包携带。
