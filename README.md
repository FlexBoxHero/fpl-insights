# FPL Insights

Projections, chip timing, and a My Team pitch for Fantasy Premier League. Angular 19 UI, FastAPI, Postgres.

## Local

```powershell
# API (from repo root, venv already created)
.venv\Scripts\python -m uvicorn app.main:app --app-dir services/api --reload --port 8001

# UI
cd apps/web
npm start
```

Optional Postgres: `docker compose -f infra/docker-compose.yml up db`. Copy `.env.example` to `.env`.

## Deploy

One public URL via [Render](https://render.com) (app) + [Neon](https://neon.tech) (database) + GitHub Actions (weekly refresh).

1. Create a Neon project and copy the connection string. Change `postgres://` or `postgresql://` to `postgresql+psycopg://`. Keep `sslmode=require`.
2. Create a Render **Web Service** from this GitHub repo.
   - Runtime: Docker
   - Dockerfile path: `infra/Dockerfile`
   - `DATABASE_URL` — Neon URL (pooled host is fine for the website)
   - `CORS_ORIGINS` — `https://<your-service>.onrender.com`
   - Optional: `VISION_API_KEY`, `VISION_API_BASE`, `VISION_MODEL` for My Team screenshot ingest
3. In GitHub **Settings → Secrets and variables → Actions**, add `DATABASE_URL` using Neon’s **direct** host (not `-pooler`).
4. **Actions → Weekly FPL ETL and inference → Run workflow**, mode **full**. The first seed can take a while; if it times out, run **full** again — it resumes from rows already written. Wait for a green run before expecting predictions.
5. Open the Render URL. After idle time the first load can take 30–60 seconds.

Monday 06:00 UTC the weekly job refreshes live FPL data and predictions. You can also run it manually after a gameweek (`weekly` mode).
