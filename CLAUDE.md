# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Backend (requires MySQL + MongoDB running)
cd backend
uvicorn main:app --reload        # starts on 127.0.0.1:8000

# Frontend
cd frontend
npm install
npm run dev                      # starts on localhost:5173

# Package as standalone .exe (run from backend/)
.\build.bat
```

## Architecture

**Dual-mode system** controlled by `backend/.env` → `APP_MODE`:
- `development`: FastAPI backend + Vite dev server, MySQL + MongoDB
- `standalone`: FastAPI serves built Vue from `backend/static/`, SQLite + local JSON files

**Request flow:**
```
Vue (Simulator.vue) → POST /api/v1/simulate/run
  → DataFetcher (AkShare → Polars DataFrame)
  → Strategy.execute() (grid trading loop)
  → SimulationResponse (metrics + equity_curve + execution_records)
  → optional: save to MySQL + MongoDB via /api/v1/records/save-favorite
  → optional: SSE AI analysis via /api/v1/ai/analyze-stream
```

**Split storage pattern** — the key architectural decision:
- `simulation_records` table (MySQL/SQLite): lightweight index fields only — symbol, dates, metrics, `strategy_params` JSON, and a `mongo_log_id` foreign key
- MongoDB collection `simulation_logs` (dev) / `data/logs/{uuid}.json` (standalone): heavy arrays — `equity_curve` and `execution_records`
- The two are linked solely by `mongo_log_id`; never join them at the DB layer

**Strategy pattern:**
- `backend/app/strategy/base.py` — `BaseStrategy` ABC with `_buy()`, `_sell()`, `_record_equity_snapshot()`, `_calculate_metrics()`
- To add a new strategy: subclass `BaseStrategy`, implement `execute()`, register by `strategy_name` string in `backend/app/api/v1/simulate.py`
- `GridTradingStrategy` uses `GridNode` objects (IDLE/OCCUPIED state machine) — each grid level must complete a buy→sell pair before it can buy again

**Mode-sensitive files** (the only three files that branch on `APP_MODE`):
- `backend/app/core/config.py` — exposes `settings.is_standalone`
- `backend/app/db/session.py` — selects SQLAlchemy engine; conditionally imports Motor
- `backend/app/api/v1/records.py` — writes/reads MongoDB vs local JSON

**AI streaming:** `POST /api/v1/ai/analyze-stream` uses `openai.AsyncOpenAI` with a configurable `base_url` (defaults to Aliyun DashScope). Returns `text/event-stream` SSE. Configure via `.env`: `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`.

## Key .env Variables

```dotenv
APP_MODE=development
MYSQL_URL=mysql+pymysql://root:root@127.0.0.1:3306/tradesim
MONGO_URL=mongodb://127.0.0.1:27017
LLM_API_KEY=
LLM_MODEL=qwen-max
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

## Database Init

```bash
# MySQL schema (development only)
mysql -u root -p < db_init.sql
```

SQLite is created automatically on first run in standalone mode.
