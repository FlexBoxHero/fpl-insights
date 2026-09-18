# FPL Insights — setup on a new machine

This package is a **minimal source copy** (no `node_modules`, Python virtualenv, local database, or git history). Follow these steps to install dependencies, load data, and run the app.

## What you need installed first

| Tool | Version |
|------|---------|
| **Python** | 3.11 or newer ([python.org](https://www.python.org/downloads/)) — on Windows, check “Add Python to PATH” |
| **Node.js** | 18 LTS or newer ([nodejs.org](https://nodejs.org/)) — includes `npm` |
| **Internet** | Required for `npm install`, `pip install`, and the first ETL run (FPL API, historical CSVs) |

PostgreSQL and Docker are **optional**. Default setup uses **SQLite** (`fpl_insights.db` created in the project root).

## 1. Unzip the project

Extract the archive to a folder, for example:

- Windows: `C:\Projects\fpl-insights`
- macOS/Linux: `~/Projects/fpl-insights`

All commands below assume your terminal’s **current directory is the project root** (the folder that contains `apps`, `services`, `scripts`, and `requirements-dev.txt`).

## 2. Environment file (optional but recommended)

```text
copy .env.example .env
```

On macOS/Linux: `cp .env.example .env`

Defaults are fine for local SQLite. Edit `.env` only if you use PostgreSQL or need to change CORS/API settings.

## 3. Python environment and packages

From the **project root**:

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the API, ETL, ML, and shared packages from this repo in editable mode.

## 4. Database and data (first-time only)

Still in the project root, with the virtualenv activated:

```bash
python scripts/init_db.py
python scripts/run_etl.py
python scripts/run_inference.py
```

- **init_db** — creates schema (Alembic migrations).
- **run_etl** — downloads/refreshes FPL and related data (can take several minutes).
- **run_inference** — writes team/player predictions into the database.

To refresh data later (e.g. after a gameweek), run `run_etl.py` and `run_inference.py` again. You can also use `python scripts/weekly_pipeline.py` as a single entry point.

## 5. Start the API (port 8001)

The Angular app is configured to call **http://localhost:8001** (`apps/web/src/environments/environment.ts`).

**Windows:**

```powershell
cd services\api
..\..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8001
```

**macOS/Linux:**

```bash
cd services/api
../../.venv/bin/python -m uvicorn app.main:app --reload --port 8001
```

Leave this terminal open. Check: [http://localhost:8001/docs](http://localhost:8001/docs) (FastAPI Swagger).

> If port 8001 is already in use, stop the other process or pick another port and update `apiBaseUrl` in `apps/web/src/environments/environment.ts` to match.

## 6. Start the web app (port 4200)

Open a **second** terminal:

```bash
cd apps/web
npm ci
npm start
```

If `npm ci` fails (no lockfile), use `npm install` instead.

Open [http://localhost:4200](http://localhost:4200) in your browser.

## 7. Full reset (optional)

To wipe local data and rebuild from scratch:

1. Stop the API and Angular dev servers.
2. Delete `fpl_insights.db` in the project root (if present).
3. Run again: `init_db.py` → `run_etl.py` → `run_inference.py`.
4. Restart API and web as above.

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| `ModuleNotFoundError` for `fpl_shared` / `app` | Activate `.venv` and re-run `pip install -r requirements-dev.txt` from the **repo root**. |
| API errors / empty UI | Confirm ETL and inference finished without errors; check that `fpl_insights.db` exists in the repo root. |
| CORS errors in browser | Ensure `CORS_ORIGINS` in `.env` includes `http://localhost:4200`. |
| SSL errors during ETL | Set `HTTP_VERIFY_SSL=false` in `.env` only if your network uses SSL inspection (use with care). |
| Port already in use (Windows) | `Get-NetTCPConnection -LocalPort 8001 -State Listen` then `taskkill /F /PID <OwningProcess>` (same for 4200). |

## Project layout (short)

| Path | Role |
|------|------|
| `apps/web` | Angular frontend |
| `services/api` | FastAPI backend |
| `services/etl` | Data ingestion |
| `services/ml` | Models and inference |
| `packages/fpl_shared` | Shared DB models, config, migrations |
| `scripts/` | `init_db`, ETL, inference, weekly pipeline |
| `docs/DATA_SOURCES.md` | Data attribution and sources |

## Sharing this zip again

When re-packaging for someone else, **exclude**:

- `node_modules/`, `.venv/`, `.angular/`, `dist/`
- `fpl_insights.db` and any `.env` (secrets)
- `.git/` if present

Include `.env.example` and this file.

---

For a one-line overview of features, see `README.md` in this folder.
