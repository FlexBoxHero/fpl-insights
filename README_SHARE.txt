FPL Insights — shareable source package
=======================================

Start here: open SETUP_INSTRUCTIONS.md and follow steps 1–6.

Quick summary:
  1. Python 3.11+ venv + pip install -r requirements-dev.txt (from repo root)
  2. python scripts/init_db.py && run_etl.py && run_inference.py
  3. API: uvicorn on port 8001 (see SETUP_INSTRUCTIONS.md)
  4. Web: cd apps/web && npm ci && npm start → http://localhost:4200

This archive intentionally omits node_modules, .venv, database files, and .env.
