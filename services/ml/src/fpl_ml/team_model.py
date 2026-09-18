"""Team fixture outcome predictions via Dixon-Coles Poisson + logistic clean sheets."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

from fpl_shared.config import settings
from fpl_shared.models import (
    Fixture,
    PredictionTeamFixture,
    Season,
    Team,
    TeamRating,
)

MAX_GOALS = 8
# Premier League scoring rates (home edge is in the two bases, not a separate multiplier).
LEAGUE_AVG_HOME = 1.52
LEAGUE_AVG_AWAY = 1.21
# Exponential recency: half-life of ~8 matches.
RATING_DECAY = 0.917
RATING_PRIOR_STRENGTH = 8.0
MIN_OPP_DEFENSE_DIVISOR = 0.68
LAMBDA_CAP = 3.15
# Dixon-Coles correlation; negative rho lifts 0-0 / 1-1 (draws) vs independent Poisson.
DC_RHO = -0.10
WEAK_PRIOR = {
    "attack_home": 0.76,
    "attack_away": 0.72,
    "defense_home": 0.78,
    "defense_away": 0.76,
}
PRIOR_BLEND_GAMES = 4.0


def _matches_played(fixtures: list[Fixture]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for fx in _finished_fixtures(fixtures):
        counts[fx.home_team_id] += 1
        counts[fx.away_team_id] += 1
    return counts


def previous_season_ratings_by_short_name(db: Session, season: Season) -> dict[str, dict[str, float]]:
    """Final ratings from the most recent previous season, keyed by FPL short name."""
    prev = (
        db.query(Season)
        .filter(Season.code < season.code)
        .order_by(Season.code.desc())
        .first()
    )
    if not prev:
        return {}
    prev_teams = {t.id: t for t in db.query(Team).filter(Team.season_id == prev.id).all()}
    if not prev_teams:
        return {}
    prev_fx = (
        db.query(Fixture)
        .filter(Fixture.season_id == prev.id, Fixture.finished.is_(True))
        .all()
    )
    ratings = _compute_ratings_from_fixtures(prev_fx, prev_teams)
    out: dict[str, dict[str, float]] = {}
    for tid, team in prev_teams.items():
        if tid in ratings and team.short_name:
            out[team.short_name] = ratings[tid]
    return out


def blend_ratings_with_prior(
    current: dict[int, dict[str, float]],
    teams: dict[int, Team],
    matches_played: dict[int, int],
    prior_by_short_name: dict[str, dict[str, float]],
) -> dict[int, dict[str, float]]:
    """Shrink early-season ratings toward last season (or a promoted-team prior)."""
    blended: dict[int, dict[str, float]] = {}
    for tid, team in teams.items():
        n = float(matches_played.get(tid, 0))
        observed = current.get(tid, dict(WEAK_PRIOR))
        prior = prior_by_short_name.get(getattr(team, "short_name", "") or "")
        if prior is None:
            blended[tid] = observed if n > 0 else dict(WEAK_PRIOR)
            continue
        # Last season mean-reverts slightly; current form takes over after ~8 matches.
        prior_shrunk = {k: 0.75 * prior.get(k, 1.0) + 0.25 * 1.0 for k in WEAK_PRIOR}
        weight = n / (n + PRIOR_BLEND_GAMES)
        blended[tid] = {
            k: weight * observed.get(k, 1.0) + (1.0 - weight) * prior_shrunk[k] for k in WEAK_PRIOR
        }
    return blended


def ratings_as_of_fixtures(
    fixtures: list[Fixture],
    teams: dict[int, Team],
    prior_by_short_name: dict[str, dict[str, float]] | None = None,
) -> dict[int, dict[str, float]]:
    current = _compute_ratings_from_fixtures(fixtures, teams)
    return blend_ratings_with_prior(
        current, teams, _matches_played(fixtures), prior_by_short_name or {}
    )


def _finished_fixtures(fixtures: list[Fixture]) -> list[Fixture]:
    ordered = [
        fx
        for fx in fixtures
        if fx.finished and fx.home_score is not None and fx.away_score is not None
    ]
    return sorted(ordered, key=lambda fx: (fx.gameweek_number or 0, getattr(fx, "id", 0) or 0))


def _shrink_to_one(value: float, n_eff: float, prior: float = 1.0) -> float:
    weight = n_eff / (n_eff + RATING_PRIOR_STRENGTH)
    shrunk = prior + weight * (value - prior)
    return float(max(0.35, min(2.6, shrunk)))


def _compute_ratings_from_fixtures(
    fixtures: list[Fixture], teams: dict[int, Team]
) -> dict[int, dict[str, float]]:
    """Recency-weighted attack/defense, split by home/away, shrunk toward league average."""
    finished = _finished_fixtures(fixtures)
    n_matches = len(finished)
    weights = [RATING_DECAY ** (n_matches - 1 - i) for i in range(n_matches)]

    home_gf: dict[int, list[tuple[float, float]]] = defaultdict(list)
    home_ga: dict[int, list[tuple[float, float]]] = defaultdict(list)
    away_gf: dict[int, list[tuple[float, float]]] = defaultdict(list)
    away_ga: dict[int, list[tuple[float, float]]] = defaultdict(list)
    played: dict[int, float] = defaultdict(float)

    league_home_num = league_home_den = 0.0
    league_away_num = league_away_den = 0.0
    for fx, w in zip(finished, weights):
        home_gf[fx.home_team_id].append((fx.home_score, w))
        home_ga[fx.home_team_id].append((fx.away_score, w))
        away_gf[fx.away_team_id].append((fx.away_score, w))
        away_ga[fx.away_team_id].append((fx.home_score, w))
        played[fx.home_team_id] += 1
        played[fx.away_team_id] += 1
        league_home_num += w * fx.home_score
        league_home_den += w
        league_away_num += w * fx.away_score
        league_away_den += w

    league_home = (league_home_num / league_home_den) if league_home_den else LEAGUE_AVG_HOME
    league_away = (league_away_num / league_away_den) if league_away_den else LEAGUE_AVG_AWAY
    league_home = float(np.clip(league_home, 1.05, 1.85))
    league_away = float(np.clip(league_away, 0.85, 1.55))

    def _weighted_mean(pairs: list[tuple[float, float]], default: float) -> tuple[float, float]:
        if not pairs:
            return default, 0.0
        num = sum(val * w for val, w in pairs)
        den = sum(w for _, w in pairs)
        if den <= 1e-9:
            return default, 0.0
        return num / den, den

    ratings: dict[int, dict[str, float]] = {}
    for tid in teams:
        h_gf, h_n = _weighted_mean(home_gf[tid], league_home)
        h_ga, _ = _weighted_mean(home_ga[tid], league_away)
        a_gf, a_n = _weighted_mean(away_gf[tid], league_away)
        a_ga, _ = _weighted_mean(away_ga[tid], league_home)
        n = played.get(tid, 0.0)
        if n <= 0:
            ratings[tid] = dict(WEAK_PRIOR)
            continue
        att_h = _shrink_to_one(h_gf / max(league_home, 0.5), h_n)
        att_a = _shrink_to_one(a_gf / max(league_away, 0.5), a_n)
        def_h = _shrink_to_one(league_away / max(h_ga, 0.35), h_n)
        def_a = _shrink_to_one(league_home / max(a_ga, 0.35), a_n)
        ratings[tid] = {
            "attack_home": att_h,
            "attack_away": att_a,
            "defense_home": def_h,
            "defense_away": def_a,
        }
    return ratings


def _expected_goals(
    home_attack: float, home_defense: float, away_attack: float, away_defense: float
) -> tuple[float, float]:
    """Attack/defense are multipliers vs league average; higher defense = fewer goals conceded."""
    lam_home = LEAGUE_AVG_HOME * home_attack / max(away_defense, MIN_OPP_DEFENSE_DIVISOR)
    lam_away = LEAGUE_AVG_AWAY * away_attack / max(home_defense, MIN_OPP_DEFENSE_DIVISOR)
    lam_home = min(LAMBDA_CAP, max(0.08, lam_home))
    lam_away = min(LAMBDA_CAP, max(0.08, lam_away))
    return lam_home, lam_away


def _dc_tau(home_goals: int, away_goals: int, lam_home: float, lam_away: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lam_home * lam_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lam_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lam_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def _scoreline_joint(lam_home: float, lam_away: float, rho: float = DC_RHO) -> np.ndarray:
    home_p = poisson.pmf(np.arange(MAX_GOALS + 1), lam_home)
    away_p = poisson.pmf(np.arange(MAX_GOALS + 1), lam_away)
    joint = np.outer(home_p, away_p)
    joint[0, 0] *= _dc_tau(0, 0, lam_home, lam_away, rho)
    joint[0, 1] *= _dc_tau(0, 1, lam_home, lam_away, rho)
    joint[1, 0] *= _dc_tau(1, 0, lam_home, lam_away, rho)
    joint[1, 1] *= _dc_tau(1, 1, lam_home, lam_away, rho)
    joint = np.maximum(joint, 0.0)
    total = float(joint.sum())
    if total <= 0:
        joint[0, 0] = 1.0
        return joint
    return joint / total


def _outcome_probs(
    lam_home: float, lam_away: float, rho: float = DC_RHO
) -> tuple[float, float, float]:
    joint = _scoreline_joint(lam_home, lam_away, rho)
    hs, aws = np.indices(joint.shape)
    home_win = float(joint[hs > aws].sum())
    draw = float(joint[hs == aws].sum())
    away_win = float(joint[hs < aws].sum())
    total = home_win + draw + away_win
    if total <= 0:
        return 1.0 / 3, 1.0 / 3, 1.0 / 3
    return home_win / total, draw / total, away_win / total


def clean_sheet_probs(
    lam_home: float, lam_away: float, rho: float = DC_RHO
) -> tuple[float, float]:
    joint = _scoreline_joint(lam_home, lam_away, rho)
    home_cs = float(joint[:, 0].sum())
    away_cs = float(joint[0, :].sum())
    return home_cs, away_cs


def _cs_feature_row(lam_opponent: float, team_defense: float, is_home: bool) -> np.ndarray:
    poisson_cs = float(np.clip(np.exp(-max(lam_opponent, 0.0)), 0.02, 0.90))
    return np.array([[lam_opponent, team_defense, int(is_home), poisson_cs]], dtype=float)


def _build_cs_training(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = np.column_stack(
        [
            df["opp_attack"].to_numpy(dtype=float),
            df["team_defense"].to_numpy(dtype=float),
            df["is_home"].to_numpy(dtype=float),
            df["poisson_cs"].to_numpy(dtype=float),
        ]
    )
    y = df["clean_sheet"].to_numpy()
    return X, y


def train_clean_sheet_model(historical: pd.DataFrame) -> LogisticRegression | None:
    if historical.empty or historical["clean_sheet"].nunique() < 2:
        return None
    X, y = _build_cs_training(historical)
    model = LogisticRegression(max_iter=500, C=0.8)
    model.fit(X, y)
    return model


def predict_clean_sheet_prob(
    lam_opponent: float,
    team_defense: float,
    is_home: bool,
    cs_model: LogisticRegression | None,
) -> float:
    """P(clean sheet); blend logistic with Poisson P(0) so early-season fits cannot invert."""
    poisson_cs = float(np.clip(np.exp(-max(lam_opponent, 0.0)), 0.03, 0.82))
    if cs_model is not None:
        ml = float(cs_model.predict_proba(_cs_feature_row(lam_opponent, team_defense, is_home))[0, 1])
        return float(np.clip(0.6 * ml + 0.4 * poisson_cs, 0.03, 0.82))
    prior = 0.28
    return float(np.clip(0.55 * poisson_cs + 0.45 * prior, 0.05, 0.75))


def predict_score_prob(lam_for: float) -> float:
    """P(team scores at least once)."""
    return float(1.0 - poisson.pmf(0, lam_for))


def build_historical_cs_rows(db: Session, season: Season) -> pd.DataFrame:
    rows: list[dict] = []
    fixtures = (
        db.query(Fixture)
        .filter(Fixture.season_id == season.id, Fixture.finished.is_(True))
        .order_by(Fixture.gameweek_number)
        .all()
    )
    teams = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
    season_prior = previous_season_ratings_by_short_name(db, season)
    prior: list[Fixture] = []
    for fx in fixtures:
        ratings = ratings_as_of_fixtures(prior, teams, season_prior)
        hr = ratings.get(fx.home_team_id, {})
        ar = ratings.get(fx.away_team_id, {})
        lam_h, lam_a = _expected_goals(
            hr.get("attack_home", 1),
            hr.get("defense_home", 1),
            ar.get("attack_away", 1),
            ar.get("defense_away", 1),
        )
        rows.append(
            {
                "opp_attack": lam_a,
                "team_defense": hr.get("defense_home", 1),
                "is_home": 1,
                "poisson_cs": float(np.exp(-lam_a)),
                "clean_sheet": 1 if fx.away_score == 0 else 0,
            }
        )
        rows.append(
            {
                "opp_attack": lam_h,
                "team_defense": ar.get("defense_away", 1),
                "is_home": 0,
                "poisson_cs": float(np.exp(-lam_h)),
                "clean_sheet": 1 if fx.home_score == 0 else 0,
            }
        )
        prior.append(fx)
    return pd.DataFrame(rows)


def persist_team_ratings(db: Session, season: Season, as_of_gw: int) -> None:
    teams = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
    finished = (
        db.query(Fixture)
        .filter(
            Fixture.season_id == season.id,
            Fixture.finished.is_(True),
            Fixture.gameweek_number.isnot(None),
            Fixture.gameweek_number < as_of_gw,
        )
        .all()
    )
    ratings = _compute_ratings_from_fixtures(finished, teams)
    season_prior = previous_season_ratings_by_short_name(db, season)
    ratings = blend_ratings_with_prior(ratings, teams, _matches_played(finished), season_prior)
    for tid, r in ratings.items():
        existing = (
            db.query(TeamRating)
            .filter(
                TeamRating.season_id == season.id,
                TeamRating.team_id == tid,
                TeamRating.as_of_gameweek == as_of_gw,
            )
            .first()
        )
        if existing:
            existing.attack_home = r["attack_home"]
            existing.attack_away = r["attack_away"]
            existing.defense_home = r["defense_home"]
            existing.defense_away = r["defense_away"]
        else:
            db.add(
                TeamRating(
                    season_id=season.id,
                    team_id=tid,
                    as_of_gameweek=as_of_gw,
                    attack_home=r["attack_home"],
                    attack_away=r["attack_away"],
                    defense_home=r["defense_home"],
                    defense_away=r["defense_away"],
                )
            )
    db.commit()


def predict_team_fixtures_for_gw(db: Session, gameweek: int, model_version: str | None = None) -> int:
    model_version = model_version or settings.model_version
    season = db.query(Season).filter(Season.is_current.is_(True)).first()
    if not season:
        season = db.query(Season).order_by(Season.id.desc()).first()
    if not season:
        return 0

    teams = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
    finished = (
        db.query(Fixture)
        .filter(
            Fixture.season_id == season.id,
            Fixture.finished.is_(True),
            Fixture.gameweek_number.isnot(None),
            Fixture.gameweek_number < gameweek,
        )
        .all()
    )
    ratings = ratings_as_of_fixtures(
        finished, teams, previous_season_ratings_by_short_name(db, season)
    )
    persist_team_ratings(db, season, gameweek)

    hist = build_historical_cs_rows(db, season)
    cs_model = train_clean_sheet_model(hist)

    upcoming = (
        db.query(Fixture)
        .filter(Fixture.season_id == season.id, Fixture.gameweek_number == gameweek)
        .all()
    )
    count = 0
    for fx in upcoming:
        hr = ratings.get(fx.home_team_id, {})
        ar = ratings.get(fx.away_team_id, {})
        lam_h, lam_a = _expected_goals(
            hr.get("attack_home", 1),
            hr.get("defense_home", 1),
            ar.get("attack_away", 1),
            ar.get("defense_away", 1),
        )
        hw, d, aw = _outcome_probs(lam_h, lam_a)
        dc_home_cs, dc_away_cs = clean_sheet_probs(lam_h, lam_a)
        home_cs = 0.55 * predict_clean_sheet_prob(
            lam_a, hr.get("defense_home", 1), True, cs_model
        ) + 0.45 * dc_home_cs
        away_cs = 0.55 * predict_clean_sheet_prob(
            lam_h, ar.get("defense_away", 1), False, cs_model
        ) + 0.45 * dc_away_cs
        home_score_p = 1.0 - dc_away_cs
        away_score_p = 1.0 - dc_home_cs

        pred = (
            db.query(PredictionTeamFixture)
            .filter(
                PredictionTeamFixture.fixture_id == fx.id,
                PredictionTeamFixture.gameweek_number == gameweek,
                PredictionTeamFixture.model_version == model_version,
            )
            .first()
        )
        if not pred:
            pred = PredictionTeamFixture(
                fixture_id=fx.id,
                gameweek_number=gameweek,
                model_version=model_version,
            )
            db.add(pred)
        pred.home_win_prob = hw
        pred.draw_prob = d
        pred.away_win_prob = aw
        pred.home_clean_sheet_prob = float(np.clip(home_cs, 0.03, 0.82))
        pred.away_clean_sheet_prob = float(np.clip(away_cs, 0.03, 0.82))
        pred.home_score_prob = float(np.clip(home_score_p, 0.15, 0.97))
        pred.away_score_prob = float(np.clip(away_score_p, 0.15, 0.97))
        pred.created_at = datetime.now(timezone.utc)
        count += 1
    db.commit()
    return count
