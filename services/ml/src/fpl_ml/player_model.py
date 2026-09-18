"""Player expected points model using LightGBM on rolling FPL features."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from fpl_ml.team_model import (
    _expected_goals,
    previous_season_ratings_by_short_name,
    ratings_as_of_fixtures,
)
from fpl_shared.config import settings
from fpl_shared.models import (
    Fixture,
    Player,
    PlayerGameweekStat,
    PredictionPlayerGameweek,
    Season,
    Team,
)

FEATURE_COLS = [
    "roll3_points",
    "roll5_points",
    "roll8_points",
    "ewm_points",
    "roll3_minutes",
    "roll5_minutes",
    "start_rate5",
    "play_rate5",
    "last_minutes",
    "roll3_xg",
    "roll5_xg",
    "roll3_xa",
    "roll5_xa",
    "roll3_xgi",
    "roll5_xgi",
    "roll3_threat",
    "roll5_threat",
    "roll3_creativity",
    "roll5_creativity",
    "roll3_bps",
    "roll5_bps",
    "roll3_bonus",
    "roll3_goals",
    "roll3_assists",
    "roll5_cs",
    "is_gk",
    "is_def",
    "is_mid",
    "is_fwd",
    "opp_fdr",
    "is_home",
    "n_fixtures",
    "lam_for",
    "lam_against",
    "opp_attack",
]

# FPL ep_next is a minutes-aware official baseline known at inference time.
# It is NOT used as a training feature (Player.ep_next is a current snapshot → leakage).
# Adaptive blend: trust FPL more for likely starters and when they mark someone out.
EP_NEXT_BLEND_MIN = 0.32
EP_NEXT_BLEND_MAX = 0.55
EP_NEXT_OUT_BLEND = 0.88
DEFAULT_RATINGS = {
    "attack_home": 1.0,
    "attack_away": 1.0,
    "defense_home": 1.0,
    "defense_away": 1.0,
}


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _ewm(values: list[float], alpha: float = 0.45) -> float:
    if not values:
        return 0.0
    acc = float(values[0])
    for value in values[1:]:
        acc = alpha * float(value) + (1.0 - alpha) * acc
    return float(acc)


def _attr_list(window: list[PlayerGameweekStat], attr: str) -> list[float]:
    return [float(getattr(row, attr, 0) or 0) for row in window]


def rolling_features(history: list[PlayerGameweekStat]) -> dict[str, float]:
    """Causal rolling stats from finished gameweeks only."""
    last3 = history[-3:]
    last5 = history[-5:]
    last8 = history[-8:]
    last_gw = history[-1]
    xg3 = _mean(_attr_list(last3, "expected_goals"))
    xa3 = _mean(_attr_list(last3, "expected_assists"))
    xg5 = _mean(_attr_list(last5, "expected_goals"))
    xa5 = _mean(_attr_list(last5, "expected_assists"))
    mins5 = _attr_list(last5, "minutes")
    return {
        "roll3_points": _mean(_attr_list(last3, "total_points")),
        "roll5_points": _mean(_attr_list(last5, "total_points")),
        "roll8_points": _mean(_attr_list(last8, "total_points")),
        "ewm_points": _ewm(_attr_list(history[-12:], "total_points")),
        "roll3_minutes": _mean(_attr_list(last3, "minutes")),
        "roll5_minutes": _mean(mins5),
        "start_rate5": sum(1.0 for m in mins5 if m >= 60) / max(len(mins5), 1),
        "play_rate5": sum(1.0 for m in mins5 if m > 0) / max(len(mins5), 1),
        "last_minutes": float(last_gw.minutes or 0),
        "roll3_xg": xg3,
        "roll5_xg": xg5,
        "roll3_xa": xa3,
        "roll5_xa": xa5,
        "roll3_xgi": xg3 + xa3,
        "roll5_xgi": xg5 + xa5,
        "roll3_threat": _mean(_attr_list(last3, "threat")),
        "roll5_threat": _mean(_attr_list(last5, "threat")),
        "roll3_creativity": _mean(_attr_list(last3, "creativity")),
        "roll5_creativity": _mean(_attr_list(last5, "creativity")),
        "roll3_bps": _mean(_attr_list(last3, "bps")),
        "roll5_bps": _mean(_attr_list(last5, "bps")),
        "roll3_bonus": _mean(_attr_list(last3, "bonus")),
        "roll3_goals": _mean(_attr_list(last3, "goals_scored")),
        "roll3_assists": _mean(_attr_list(last3, "assists")),
        "roll5_cs": _mean(_attr_list(last5, "clean_sheets")),
        "baseline_last_gw": float(last_gw.total_points or 0),
    }


def _index_fixtures(fixtures: list[Fixture]) -> dict[tuple[int, int], list[Fixture]]:
    index: dict[tuple[int, int], list[Fixture]] = defaultdict(list)
    for fx in fixtures:
        if fx.gameweek_number is None:
            continue
        index[(fx.home_team_id, fx.gameweek_number)].append(fx)
        index[(fx.away_team_id, fx.gameweek_number)].append(fx)
    return index


def _ratings_by_gameweek(
    fixtures: list[Fixture],
    teams: dict[int, Team],
    prior_by_short_name: dict[str, dict[str, float]] | None = None,
) -> dict[int, dict[int, dict[str, float]]]:
    gws = sorted({fx.gameweek_number for fx in fixtures if fx.gameweek_number})
    by_gw: dict[int, dict[int, dict[str, float]]] = {}
    for gw in gws:
        prior = [
            fx
            for fx in fixtures
            if fx.finished and fx.gameweek_number is not None and fx.gameweek_number < gw
        ]
        by_gw[gw] = ratings_as_of_fixtures(prior, teams, prior_by_short_name)
    return by_gw


def fixture_context(
    player: Player,
    gw_fixtures: list[Fixture],
    ratings: dict[int, dict[str, float]],
) -> dict[str, float] | None:
    if not player.team_id or not gw_fixtures:
        return None
    n = 0
    home_flags: list[float] = []
    fdrs: list[float] = []
    lam_for_sum = 0.0
    lam_against_sum = 0.0
    opp_attack_sum = 0.0
    for fx in gw_fixtures:
        is_home = fx.home_team_id == player.team_id
        opp_id = fx.away_team_id if is_home else fx.home_team_id
        team_r = ratings.get(player.team_id, DEFAULT_RATINGS)
        opp_r = ratings.get(opp_id, DEFAULT_RATINGS)
        if is_home:
            lam_for, lam_against = _expected_goals(
                team_r.get("attack_home", 1),
                team_r.get("defense_home", 1),
                opp_r.get("attack_away", 1),
                opp_r.get("defense_away", 1),
            )
            fdr = fx.home_difficulty
            opp_attack = opp_r.get("attack_away", 1)
        else:
            lam_against, lam_for = _expected_goals(
                opp_r.get("attack_home", 1),
                opp_r.get("defense_home", 1),
                team_r.get("attack_away", 1),
                team_r.get("defense_away", 1),
            )
            fdr = fx.away_difficulty
            opp_attack = opp_r.get("attack_home", 1)
        n += 1
        home_flags.append(1.0 if is_home else 0.0)
        fdrs.append(float(fdr if fdr is not None else 3))
        lam_for_sum += lam_for
        lam_against_sum += lam_against
        opp_attack_sum += float(opp_attack)
    if n == 0:
        return None
    return {
        "n_fixtures": float(n),
        "is_home": _mean(home_flags),
        "opp_fdr": _mean(fdrs),
        "lam_for": lam_for_sum,
        "lam_against": lam_against_sum,
        "opp_attack": opp_attack_sum / n,
    }


def _position_flags(player: Player) -> dict[str, int]:
    return {
        "is_gk": 1 if player.position == "GK" else 0,
        "is_def": 1 if player.position == "DEF" else 0,
        "is_mid": 1 if player.position == "MID" else 0,
        "is_fwd": 1 if player.position == "FWD" else 0,
    }


def _build_training_frame(db: Session, seasons: list[Season]) -> pd.DataFrame:
    rows: list[dict] = []
    n_seasons = max(len(seasons), 1)
    for season_rank, season in enumerate(seasons):
        stats = (
            db.query(PlayerGameweekStat)
            .filter(PlayerGameweekStat.season_id == season.id)
            .order_by(PlayerGameweekStat.fpl_element_id, PlayerGameweekStat.gameweek_number)
            .all()
        )
        players = {
            p.fpl_element_id: p for p in db.query(Player).filter(Player.season_id == season.id).all()
        }
        by_element: dict[int, list[PlayerGameweekStat]] = defaultdict(list)
        for s in stats:
            by_element[s.fpl_element_id].append(s)

        fixtures = db.query(Fixture).filter(Fixture.season_id == season.id).all()
        team_by_id = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
        fx_index = _index_fixtures(fixtures)
        ratings_by_gw = _ratings_by_gameweek(
            fixtures, team_by_id, previous_season_ratings_by_short_name(db, season)
        )
        recency = 0.55 + 0.45 * (season_rank / max(n_seasons - 1, 1)) if n_seasons > 1 else 1.0

        for element_id, history in by_element.items():
            history = sorted(history, key=lambda x: x.gameweek_number)
            player = players.get(element_id)
            if not player:
                continue
            for i, _gw_stat in enumerate(history):
                if i + 1 >= len(history):
                    continue
                target = history[i + 1]
                window = history[: i + 1]
                next_gw = target.gameweek_number
                gw_fixtures = fx_index.get((player.team_id or -1, next_gw), [])
                ctx = fixture_context(player, gw_fixtures, ratings_by_gw.get(next_gw, {}))
                if not ctx:
                    continue
                row = rolling_features(window)
                row.update(ctx)
                row.update(_position_flags(player))
                row["target_points"] = float(target.total_points)
                row["player_id"] = player.id
                row["gameweek_number"] = next_gw
                row["season_id"] = season.id
                row["sample_weight"] = recency * (0.72 + 0.28 * min(next_gw, 38) / 38.0)
                rows.append(row)
    return pd.DataFrame(rows)


def train_player_model(db: Session) -> lgb.LGBMRegressor | None:
    seasons = db.query(Season).order_by(Season.code).all()
    if not seasons:
        return None
    df = _build_training_frame(db, seasons)
    if df.empty or len(df) < 200:
        return None
    X = df[FEATURE_COLS]
    y = df["target_points"]
    weights = df["sample_weight"].to_numpy(dtype=float)
    model = lgb.LGBMRegressor(
        n_estimators=500,
        learning_rate=0.045,
        num_leaves=31,
        max_depth=7,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        objective="regression",
        random_state=42,
        verbosity=-1,
    )
    df_sorted = df.sort_values(["season_id", "gameweek_number"])
    cut = int(len(df_sorted) * 0.85)
    if cut >= 180 and len(df_sorted) - cut >= 80:
        train_idx = df_sorted.index[:cut]
        val_idx = df_sorted.index[cut:]
        model.fit(
            X.loc[train_idx],
            y.loc[train_idx],
            sample_weight=df.loc[train_idx, "sample_weight"].to_numpy(dtype=float),
            eval_X=X.loc[val_idx],
            eval_y=y.loc[val_idx],
            eval_metric="l2",
            callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)],
        )
    else:
        model.fit(X, y, sample_weight=weights)
    return model


def _prior_season_history(
    db: Session, season: Season, players: list[Player]
) -> dict[str, list[PlayerGameweekStat]]:
    """Map web_name -> last season's GW stats so transferred players keep a history prior."""
    prior_seasons = (
        db.query(Season).filter(Season.id != season.id).order_by(Season.code.desc()).all()
    )
    names = {p.web_name for p in players}
    history_by_name: dict[str, list[PlayerGameweekStat]] = {}
    for ps in prior_seasons:
        prior_players = (
            db.query(Player)
            .filter(Player.season_id == ps.id, Player.web_name.in_(names))
            .all()
        )
        if not prior_players:
            continue
        element_ids = [p.fpl_element_id for p in prior_players]
        stats = (
            db.query(PlayerGameweekStat)
            .filter(
                PlayerGameweekStat.season_id == ps.id,
                PlayerGameweekStat.fpl_element_id.in_(element_ids),
            )
            .order_by(PlayerGameweekStat.gameweek_number)
            .all()
        )
        by_element: dict[int, list[PlayerGameweekStat]] = defaultdict(list)
        for s in stats:
            by_element[s.fpl_element_id].append(s)
        for pp in prior_players:
            if pp.web_name in history_by_name:
                continue
            hist = by_element.get(pp.fpl_element_id)
            if hist:
                history_by_name[pp.web_name] = hist
        if len(history_by_name) >= len(names):
            break
    return history_by_name


def _inference_rows_for_gw(db: Session, season: Season, gameweek: int) -> pd.DataFrame:
    players = db.query(Player).filter(Player.season_id == season.id).all()
    fixtures = db.query(Fixture).filter(Fixture.season_id == season.id).all()
    team_by_id = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
    fx_index = _index_fixtures(fixtures)
    ratings = ratings_as_of_fixtures(
        [
            fx
            for fx in fixtures
            if fx.finished and fx.gameweek_number is not None and fx.gameweek_number < gameweek
        ],
        team_by_id,
        previous_season_ratings_by_short_name(db, season),
    )
    stats = (
        db.query(PlayerGameweekStat)
        .filter(
            PlayerGameweekStat.season_id == season.id,
            PlayerGameweekStat.gameweek_number < gameweek,
        )
        .order_by(PlayerGameweekStat.fpl_element_id, PlayerGameweekStat.gameweek_number)
        .all()
    )
    by_element: dict[int, list[PlayerGameweekStat]] = defaultdict(list)
    for s in stats:
        by_element[s.fpl_element_id].append(s)
    missing = [p for p in players if p.fpl_element_id not in by_element]
    prior_history = _prior_season_history(db, season, missing) if missing else {}

    rows: list[dict] = []
    for player in players:
        history = by_element.get(player.fpl_element_id) or prior_history.get(player.web_name)
        if not history:
            continue
        gw_fixtures = fx_index.get((player.team_id or -1, gameweek), [])
        ctx = fixture_context(player, gw_fixtures, ratings)
        if not ctx:
            continue
        row = rolling_features(history)
        row.update(ctx)
        row.update(_position_flags(player))
        row["player_id"] = player.id
        row["baseline_ep_next"] = float(player.ep_next or 0.0)
        row["gameweek_number"] = gameweek
        rows.append(row)
    return pd.DataFrame(rows)


def blend_with_ep_next(model_preds: np.ndarray, ep_next: np.ndarray) -> np.ndarray:
    """Stack the tree model with FPL's official next-GW baseline (known at inference time).

    Expected points is a mean, and FPL's ep_next already encodes minutes and availability.
    Weight that baseline more for regulars (high ep) and when FPL has them as out (~0).
    """
    model = np.asarray(model_preds, dtype=float)
    ep = np.clip(np.asarray(ep_next, dtype=float), 0.0, 16.0)
    starter_w = np.clip(EP_NEXT_BLEND_MIN + 0.035 * ep, EP_NEXT_BLEND_MIN, EP_NEXT_BLEND_MAX)
    weight = np.where(ep < 0.75, EP_NEXT_OUT_BLEND, starter_w)
    blended = (1.0 - weight) * model + weight * ep
    return np.maximum(0.0, blended)


def _minutes_floor(df: pd.DataFrame) -> np.ndarray:
    """Lower bound from appearance points (1 for playing, +1 for 60+ minutes)."""
    n_fx = np.clip(df["n_fixtures"].to_numpy(dtype=float), 0.0, 3.0)
    start = np.clip(df["start_rate5"].to_numpy(dtype=float), 0.0, 1.0)
    play = np.clip(df["play_rate5"].to_numpy(dtype=float), 0.0, 1.0)
    return n_fx * (play + start)


def finalize_player_xpts(df: pd.DataFrame, raw_preds: np.ndarray) -> np.ndarray:
    ep = np.clip(df["baseline_ep_next"].to_numpy(dtype=float), 0.0, 16.0)
    blended = blend_with_ep_next(raw_preds, ep)
    floor = np.where(ep >= 1.5, 0.85 * _minutes_floor(df), 0.0)
    return np.maximum(blended, floor)


def _fallback_preds(df: pd.DataFrame) -> np.ndarray:
    roll = (
        0.5 * df["roll3_points"].to_numpy()
        + 0.3 * df["roll5_points"].to_numpy()
        + 0.2 * df["ewm_points"].to_numpy()
    )
    minutes_factor = np.clip(df["roll3_minutes"].to_numpy() / 90.0, 0.15, 1.05)
    fdr_adj = 1.10 - 0.10 * (df["opp_fdr"].to_numpy() - 3.0)
    home_adj = 1.0 + 0.08 * df["is_home"].to_numpy()
    ep = np.clip(df["baseline_ep_next"].to_numpy(), 0.0, 16.0)
    n_fx = np.clip(df["n_fixtures"].to_numpy(), 1.0, 3.0)
    form_part = 0.55 * roll * minutes_factor * np.maximum(0.55, fdr_adj) * home_adj * n_fx
    return finalize_player_xpts(df, form_part + 0.20 * ep)


def predict_players_for_gw(db: Session, gameweek: int, model_version: str | None = None) -> int:
    model_version = model_version or settings.model_version
    season = db.query(Season).filter(Season.is_current.is_(True)).first()
    if not season:
        season = db.query(Season).order_by(Season.id.desc()).first()
    if not season:
        return 0

    model = train_player_model(db)
    df = _inference_rows_for_gw(db, season, gameweek)
    if df.empty:
        return 0

    if model is not None:
        preds = finalize_player_xpts(df, model.predict(df[FEATURE_COLS]))
    else:
        preds = _fallback_preds(df)

    count = 0
    for idx, row in enumerate(df.to_dict("records")):
        player_id = int(row["player_id"])
        xpts = float(max(0.0, preds[idx]))
        pred = (
            db.query(PredictionPlayerGameweek)
            .filter(
                PredictionPlayerGameweek.player_id == player_id,
                PredictionPlayerGameweek.gameweek_number == gameweek,
                PredictionPlayerGameweek.model_version == model_version,
            )
            .first()
        )
        if not pred:
            pred = PredictionPlayerGameweek(
                player_id=player_id,
                gameweek_number=gameweek,
                model_version=model_version,
            )
            db.add(pred)
        pred.expected_points = xpts
        pred.baseline_last_gw = float(row["baseline_last_gw"])
        pred.baseline_ep_next = float(row["baseline_ep_next"])
        pred.created_at = datetime.now(timezone.utc)
        count += 1
    db.commit()
    return count
