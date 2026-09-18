#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "fpl_shared" / "src"))
sys.path.insert(0, str(ROOT / "services" / "ml" / "src"))
sys.path.insert(0, str(ROOT / "services" / "etl" / "src"))
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.insights_service import freeze_weekly_difficulty_scale
from fpl_etl.logging_util import record_etl_run
from fpl_ml.run_inference import run_all_predictions
from fpl_shared.db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gameweek", type=int, default=None)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = run_all_predictions(db, args.gameweek)
        freeze_weekly_difficulty_scale(db, int(result["gameweek"]), overwrite=True)
        record_etl_run(db, "inference", "success", str(result))
        print("Inference complete:", result)
    except Exception as exc:
        record_etl_run(db, "inference", "failed", str(exc))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
