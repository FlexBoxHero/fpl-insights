"""Defensive contribution (DefCon) as a per-match threshold event.

FPL awards 2 points if a defender reaches 10+ CBI+tackles, or a midfielder/forward
reaches 12+ CBI+tackles+recoveries, in a single match. Points do not stack.

Official FPL live data publishes CBI as one combined total (not split clearances /
blocks / interceptions), plus tackles and recoveries.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression

DEF_THRESHOLD = 10
MID_FWD_THRESHOLD = 12
MIN_MINUTES = 45
LEGACY_WEIGHT = 0.30
HIT_RATE_WEIGHT = 0.15
ACTIONS_WEIGHT = 0.55
MIN_LOGISTIC_ROWS = 400
MIN_LOGISTIC_GAMEWEEKS = 8

FEATURE_KEYS = (
    "roll3_actions",
    "roll5_actions",
    "roll3_cbi",
    "roll3_tackles",
    "roll3_recoveries",
    "roll3_actions_p90",
    "hit_rate5",
    "minutes_factor",
    "ict_factor",
    "team_cs",
    "is_def",
    "is_mid",
    "is_fwd",
)

# Extra LightGBM columns kept alongside existing player-model features.
PLAYER_MODEL_DEFCON_COLS = [
    "roll3_cbi",
    "roll5_cbi",
    "roll3_tackles",
    "roll5_tackles",
    "roll3_recoveries",
    "roll5_recoveries",
    "roll3_cbit",
    "roll5_cbit",
    "roll3_cbirt",
    "roll5_cbirt",
    "roll3_cbit_p90",
    "roll3_cbirt_p90",
    "roll3_defcon_pts",
    "defcon_hit_rate5",
]


def defcon_threshold(position: str) -> int:
    return DEF_THRESHOLD if position == "DEF" else MID_FWD_THRESHOLD


def _num(stat: Any, attr: str) -> float:
    return float(getattr(stat, attr, 0) or 0)


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _p90(actions: Sequence[float], minutes: Sequence[float]) -> float:
    total_min = float(sum(minutes))
    if total_min <= 0:
        return 0.0
    return float(sum(actions)) / total_min * 90.0


def action_count(stat: Any, position: str) -> float:
    cbi = _num(stat, "clearances_blocks_interceptions")
    tackles = _num(stat, "tackles")
    recoveries = _num(stat, "recoveries")
    if position == "DEF":
        return cbi + tackles
    return cbi + tackles + recoveries


def hit_threshold(stat: Any, position: str) -> bool:
    awarded = int(_num(stat, "defensive_contribution"))
    if awarded >= 2:
        return True
    return action_count(stat, position) >= defcon_threshold(position)


def component_rolling_features(history: Sequence[Any]) -> dict[str, float]:
    """Position-agnostic CBI / tackles / recoveries for the player xPts model."""
    last3 = list(history[-3:])
    last5 = list(history[-5:])
    cbi3 = [_num(s, "clearances_blocks_interceptions") for s in last3]
    cbi5 = [_num(s, "clearances_blocks_interceptions") for s in last5]
    tackles3 = [_num(s, "tackles") for s in last3]
    tackles5 = [_num(s, "tackles") for s in last5]
    rec3 = [_num(s, "recoveries") for s in last3]
    rec5 = [_num(s, "recoveries") for s in last5]
    mins3 = [_num(s, "minutes") for s in last3]
    mins5 = [_num(s, "minutes") for s in last5]
    cbit3 = [c + t for c, t in zip(cbi3, tackles3)]
    cbit5 = [c + t for c, t in zip(cbi5, tackles5)]
    cbirt3 = [c + t + r for c, t, r in zip(cbi3, tackles3, rec3)]
    cbirt5 = [c + t + r for c, t, r in zip(cbi5, tackles5, rec5)]
    eligible5 = [s for s in last5 if _num(s, "minutes") >= MIN_MINUTES]
    hits = sum(1 for s in eligible5 if int(_num(s, "defensive_contribution")) >= 2)
    return {
        "roll3_cbi": _mean(cbi3),
        "roll5_cbi": _mean(cbi5),
        "roll3_tackles": _mean(tackles3),
        "roll5_tackles": _mean(tackles5),
        "roll3_recoveries": _mean(rec3),
        "roll5_recoveries": _mean(rec5),
        "roll3_cbit": _mean(cbit3),
        "roll5_cbit": _mean(cbit5),
        "roll3_cbirt": _mean(cbirt3),
        "roll5_cbirt": _mean(cbirt5),
        "roll3_cbit_p90": _p90(cbit3, mins3),
        "roll3_cbirt_p90": _p90(cbirt3, mins3),
        "roll3_defcon_pts": _mean([_num(s, "defensive_contribution") for s in last3]),
        "defcon_hit_rate5": (hits / len(eligible5)) if eligible5 else 0.0,
    }


def rolling_defcon_features(history: Sequence[Any], position: str) -> dict[str, float]:
    """Causal rolling CBI / tackles / recoveries plus combined action rates."""
    components = component_rolling_features(history)
    last3 = list(history[-3:])
    last5 = list(history[-5:])
    actions3 = [action_count(s, position) for s in last3]
    actions5 = [action_count(s, position) for s in last5]
    mins3 = [_num(s, "minutes") for s in last3]
    eligible5 = [s for s in last5 if _num(s, "minutes") >= MIN_MINUTES]
    hits = sum(1 for s in eligible5 if hit_threshold(s, position))
    return {
        **components,
        "roll3_actions": _mean(actions3),
        "roll5_actions": _mean(actions5),
        "roll3_actions_p90": _p90(actions3, mins3),
        "hit_rate5": (hits / len(eligible5)) if eligible5 else 0.0,
        "avg_minutes_last3": _mean(mins3),
    }


def legacy_context_probability(
    minutes_factor: float,
    ict_factor: float,
    team_cs: float,
    position: str,
) -> float:
    """Original minutes / ICT / CS heuristic, kept as a context prior."""
    pos_boost = 0.15 if position == "DEF" else 0.05
    return min(0.95, minutes_factor * 0.55 + ict_factor * 0.25 + team_cs * 0.15 + pos_boost)


def sigmoid_threshold_probability(expected_actions: float, threshold: int) -> float:
    """P(count >= threshold) with a logistic around the bar (scale ~2.5 actions)."""
    z = (expected_actions - float(threshold)) / 2.5
    z = max(-8.0, min(8.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def predicted_defcon_actions(features: dict[str, float]) -> float:
    """Expected CBIT (DEF) or CBIRT (MID/FWD) in the upcoming match."""
    minutes_factor = float(features.get("minutes_factor", 0.0))
    per90 = float(features.get("roll3_actions_p90", 0.0))
    if per90 > 0:
        return per90 * minutes_factor
    return float(features.get("roll3_actions", 0.0)) * minutes_factor


def blend_hit_probability(
    features: dict[str, float],
    position: str,
    logistic: LogisticRegression | None = None,
) -> float:
    threshold = defcon_threshold(position)
    minutes_factor = float(features.get("minutes_factor", 0.0))
    expected_actions = predicted_defcon_actions(features)
    p_actions = sigmoid_threshold_probability(expected_actions, threshold)
    p_legacy = legacy_context_probability(
        minutes_factor,
        float(features.get("ict_factor", 0.0)),
        float(features.get("team_cs", 0.15)),
        position,
    )
    p_hit_rate = float(features.get("hit_rate5", 0.0))
    if logistic is not None:
        vector = np.array([[float(features.get(key, 0.0)) for key in FEATURE_KEYS]], dtype=float)
        p_model = float(logistic.predict_proba(vector)[0, 1])
        blended = 0.70 * p_model + 0.15 * p_hit_rate + 0.15 * p_legacy
    else:
        blended = ACTIONS_WEIGHT * p_actions + HIT_RATE_WEIGHT * p_hit_rate + LEGACY_WEIGHT * p_legacy
    return float(min(0.95, max(0.03, blended)))


def expected_defcon_count(probability: float, n_matches: int = 1) -> float:
    """Expected number of DefCon awards (max one per match)."""
    matches = max(1, int(n_matches))
    return round(float(probability) * matches, 3)


def expected_defcon_points(probability: float, n_matches: int = 1) -> float:
    return round(2.0 * expected_defcon_count(probability, n_matches), 3)


def feature_row(
    history: Sequence[Any],
    position: str,
    *,
    team_cs: float = 0.15,
    ict_index_avg: float | None = None,
) -> dict[str, float] | None:
    if not history:
        return None
    rolling = rolling_defcon_features(history, position)
    avg_min = rolling["avg_minutes_last3"]
    if avg_min < MIN_MINUTES:
        return None
    last3 = history[-3:]
    ict_avg = (
        ict_index_avg
        if ict_index_avg is not None
        else _mean([_num(s, "ict_index") for s in last3])
    )
    return {
        **rolling,
        "minutes_factor": min(1.0, avg_min / 90.0),
        "ict_factor": min(1.0, ict_avg / 30.0),
        "team_cs": float(team_cs),
        "is_def": 1.0 if position == "DEF" else 0.0,
        "is_mid": 1.0 if position == "MID" else 0.0,
        "is_fwd": 1.0 if position == "FWD" else 0.0,
    }


def train_defcon_logistic(samples: list[tuple[dict[str, float], int]]) -> LogisticRegression | None:
    if len(samples) < MIN_LOGISTIC_ROWS:
        return None
    y = np.array([label for _, label in samples], dtype=int)
    if int(y.min()) == int(y.max()):
        return None
    x = np.array([[float(row.get(key, 0.0)) for key in FEATURE_KEYS] for row, _ in samples], dtype=float)
    model = LogisticRegression(max_iter=400, C=0.8)
    model.fit(x, y)
    return model


def build_training_samples(
    histories: dict[int, list[Any]],
    positions: dict[int, str],
) -> list[tuple[dict[str, float], int]]:
    """Walk-forward labels: features from GWs < t, hit/miss on GW t."""
    samples: list[tuple[dict[str, float], int]] = []
    for player_id, history in histories.items():
        position = positions.get(player_id, "")
        ordered = sorted(history, key=lambda s: int(getattr(s, "gameweek_number", 0) or 0))
        for i in range(1, len(ordered)):
            prior = ordered[:i]
            target = ordered[i]
            if _num(target, "minutes") < MIN_MINUTES:
                continue
            features = feature_row(prior, position, team_cs=0.15)
            if not features:
                continue
            samples.append((features, 1 if hit_threshold(target, position) else 0))
    return samples


_defcon_model_by_season: dict[int, LogisticRegression | None] = {}


def cached_defcon_model(
    season_id: int,
    histories: dict[int, list[Any]],
    positions: dict[int, str],
) -> LogisticRegression | None:
    if season_id not in _defcon_model_by_season:
        max_gw = 0
        for history in histories.values():
            for stat in history:
                max_gw = max(max_gw, int(getattr(stat, "gameweek_number", 0) or 0))
        if max_gw < MIN_LOGISTIC_GAMEWEEKS:
            _defcon_model_by_season[season_id] = None
        else:
            _defcon_model_by_season[season_id] = train_defcon_logistic(
                build_training_samples(histories, positions)
            )
    return _defcon_model_by_season[season_id]


def as_stat(**kwargs: Any) -> SimpleNamespace:
    defaults = {
        "minutes": 0,
        "total_points": 0,
        "clearances_blocks_interceptions": 0,
        "tackles": 0,
        "recoveries": 0,
        "defensive_contribution": 0,
        "ict_index": 0.0,
        "gameweek_number": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)
