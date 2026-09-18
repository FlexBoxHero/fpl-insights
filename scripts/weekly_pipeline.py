#!/usr/bin/env python3
"""Post-GW pipeline: sync live data then refresh predictions."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    etl = ROOT / "scripts" / "run_etl.py"
    inf = ROOT / "scripts" / "run_inference.py"
    subprocess.check_call([sys.executable, str(etl), "--skip-backfill"])
    subprocess.check_call([sys.executable, str(inf)])


if __name__ == "__main__":
    main()
