# Data sources

There is no official FPL API for past seasons. Historical and live data are loaded from a hybrid of archives, community CSVs, and the current FPL API.

## Fantasy Premier League API (current season)

- Base URL: `https://fantasy.premierleague.com/api`
- Unofficial, read-only, no API key
- Used for **2026-27** bootstrap, fixtures, and live player / GW stats
- Fresher than community CSV dumps; also avoids Core Insights GW0 friendlies

## vaastav/Fantasy-Premier-League (frozen archive)

- Historical GW CSV archives for **2018-19 through 2023-24**
- Credit: [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League)
- Older seasons (especially 2018-19) may lack `teams.csv` or `gws/merged_gw.csv`; the loader falls back to `master_team_list.csv` and per-GW `gws/gw{n}.csv`
- xG/xA columns are sparse before ~2021-22 and default to 0
- Weekly updates to that repository stopped after 2024-25; we do not re-ingest 2024-25 from this archive (existing DB rows stay)

## FPL-Core-Insights (missing 2025-26)

- Completed **2025-26** season from [olbauday/FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights)
- Teams, players, fixtures, and per-GW `player_gameweek_stats.csv` under `data/2025-2026/By Gameweek/GW{n}/`
- FPL element IDs are aligned with the official API
- Core also publishes `2026-2027`; we **do not** use it as the live source

## football-data.co.uk / Datahub EPL

- Match results for **2018-19 through 2026-27**, used for team strength features and linking to FPL fixtures
- A season is skipped if its `Season` row does not exist yet
- Credit: [football-data.co.uk](https://www.football-data.co.uk/)

## Refresh cadence

- **Initial / full history:** `python scripts/run_etl.py` (Vaastav archive + Core 2025-26 + live 2026-27 + match stats)
- **Weekly (after GW):** `python scripts/weekly_pipeline.py` (uses `--skip-backfill` so it does not re-download historical seasons)
- **Predictions only:** `python scripts/run_inference.py --gameweek N`
