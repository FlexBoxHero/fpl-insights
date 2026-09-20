"""Parse FPL DefCon component stats from live or backfill rows."""

from __future__ import annotations


def _as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        number = float(value)
        if number != number:
            return default
        return int(number)
    except (TypeError, ValueError):
        return default


def defcon_stat_fields(row: dict) -> dict[str, int]:
    """CBI is official FPL's combined clearances+blocks+interceptions field."""
    return {
        "clearances_blocks_interceptions": _as_int(
            row.get("clearances_blocks_interceptions", row.get("CBI"))
        ),
        "tackles": _as_int(row.get("tackles")),
        "recoveries": _as_int(row.get("recoveries")),
        "defensive_contribution": _as_int(row.get("defensive_contribution")),
    }
