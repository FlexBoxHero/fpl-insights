#!/usr/bin/env python3
"""Run full ETL pipeline: aliases, historical backfill, live sync, match stats."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "fpl_shared" / "src"))
sys.path.insert(0, str(ROOT / "services" / "etl" / "src"))
sys.path.insert(0, str(ROOT / "services" / "ml" / "src"))

from fpl_etl.core_insights_backfill import CORE_SEASONS, backfill_all_core_insights
from fpl_etl.fpl_live_sync import sync_current_season_from_api
from fpl_etl.sync_player_gw_stats import sync_current_season_player_gw_stats
from fpl_etl.logging_util import record_etl_run
from fpl_etl.match_stats_ingest import ingest_match_stats
from fpl_etl.seed_aliases import seed_team_aliases
from fpl_etl.vaastav_backfill import VAASTAV_SEASONS, backfill_all_vaastav
from fpl_shared import models  # noqa: F401
from fpl_shared.db import Base, SessionLocal, engine


def main() -> None:
    parser = argparse.ArgumentParser(description="FPL Insights ETL")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--skip-player-sync", action="store_true")
    parser.add_argument("--seasons", nargs="*", default=VAASTAV_SEASONS)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_team_aliases(db)
        if not args.skip_backfill:
            vaastav_stats = backfill_all_vaastav(db, args.seasons)
            core_stats = backfill_all_core_insights(db, CORE_SEASONS)
            print("Vaastav:", vaastav_stats)
            print("Core Insights:", core_stats)
        sync_current_season_from_api(db)
        gw_stats = 0
        if not args.skip_player_sync:
            gw_stats = sync_current_season_player_gw_stats(db)
        stats = ingest_match_stats(db)
        stats["player_gw_synced"] = gw_stats
        record_etl_run(db, "full_etl", "success", str(stats))
        print("ETL complete:", stats)
    except Exception as exc:
        record_etl_run(db, "full_etl", "failed", str(exc))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
