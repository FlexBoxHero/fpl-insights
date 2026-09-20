"""Parse extra per-GW FPL stats (starts, xGC) from live or backfill rows."""

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


def _as_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
        if number != number:
            return default
        return number
    except (TypeError, ValueError):
        return default


def extra_gw_stat_fields(row: dict) -> dict[str, int | float]:
    xgc = row.get("expected_goals_conceded", row.get("xGC"))
    return {
        "starts": _as_int(row.get("starts")),
        "expected_goals_conceded": _as_float(xgc),
    }
