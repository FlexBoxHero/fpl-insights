#!/usr/bin/env python3
"""Create schema (SQLite dev) or run Alembic migrations."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "fpl_shared" / "src"))

alembic_ini = ROOT / "packages" / "fpl_shared" / "alembic.ini"
if alembic_ini.exists():
    subprocess.check_call(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "packages" / "fpl_shared",
    )
else:
    from fpl_shared import models  # noqa: F401
    from fpl_shared.db import Base, engine

    Base.metadata.create_all(bind=engine)

print("Database ready.")
