"""Aggregated insights for team/player dashboards."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from sklearn.linear_model import LogisticRegression

from fpl_ml.difficulty_scale import (
    FDR_SCALE_WINDOW,
    blend_with_fpl_fdr,
    label_for_level,
    level_from_breaks,
    quantile_breaks,
    raw_difficulty_from_lambdas,
)
from fpl_ml.team_model import (
    _expected_goals,
    _outcome_probs,
    build_historical_cs_rows,
    clean_sheet_probs,
    predict_clean_sheet_prob,
    predict_score_prob,
    previous_season_ratings_by_short_name,
    ratings_as_of_fixtures,
    train_clean_sheet_model,
)
from fpl_shared.db import Base, engine
from fpl_shared.models import (
    DifficultyScale,
    Fixture,
    Player,
    PlayerGameweekStat,
    PredictionPlayerGameweek,
    PredictionTeamFixture,
    Season,
    Team,
)


def _team_display(team: Team | None) -> dict:
    if not team:
        return {"team": "", "team_name": "", "team_code": None}
    return {
        "team": team.short_name,
        "team_name": team.name,
        "team_code": team.code,
    }


def _current_season(db: Session) -> Season | None:
    season = db.query(Season).filter(Season.is_current.is_(True)).first()
    return season or db.query(Season).order_by(Season.id.desc()).first()


def _team_map(db: Session, season_id: int) -> dict[int, Team]:
    return {t.id: t for t in db.query(Team).filter(Team.season_id == season_id).all()}


_cs_model_by_season: dict[int, LogisticRegression | None] = {}


def _clean_sheet_model(db: Session, season: Season) -> LogisticRegression | None:
    if season.id not in _cs_model_by_season:
        hist = build_historical_cs_rows(db, season)
        _cs_model_by_season[season.id] = train_clean_sheet_model(hist)
    return _cs_model_by_season[season.id]


def _prediction_map(
    db: Session, gameweek_numbers: set[int]
) -> dict[tuple[int, int], PredictionTeamFixture]:
    if not gameweek_numbers:
        return {}
    preds = (
        db.query(PredictionTeamFixture)
        .filter(PredictionTeamFixture.gameweek_number.in_(gameweek_numbers))
        .all()
    )
    return {(p.fixture_id, p.gameweek_number): p for p in preds}


STRENGTH_DIFFICULTY_MODEL = "strength_v6"

_AVERAGE_PRIOR = {
    "attack_home": 1.0,
    "attack_away": 1.0,
    "defense_home": 1.0,
    "defense_away": 1.0,
}


def _ratings_as_of_gw(
    db: Session, season: Season, before_gw: int, teams: dict[int, Team]
) -> dict[int, dict[str, float]]:
    finished = (
        db.query(Fixture)
        .filter(
            Fixture.season_id == season.id,
            Fixture.finished.is_(True),
            Fixture.gameweek_number.isnot(None),
            Fixture.gameweek_number < before_gw,
        )
        .all()
    )
    return ratings_as_of_fixtures(
        finished, teams, previous_season_ratings_by_short_name(db, season)
    )


def _fixture_outcomes(
    fx: Fixture, ratings: dict[int, dict[str, float]]
) -> dict[str, float]:
    hr = ratings.get(fx.home_team_id, _AVERAGE_PRIOR)
    ar = ratings.get(fx.away_team_id, _AVERAGE_PRIOR)
    lam_h, lam_a = _expected_goals(
        hr.get("attack_home", 1.0),
        hr.get("defense_home", 1.0),
        ar.get("attack_away", 1.0),
        ar.get("defense_away", 1.0),
    )
    hw, draw, aw = _outcome_probs(lam_h, lam_a)
    home_cs, away_cs = clean_sheet_probs(lam_h, lam_a)
    return {
        "lam_home": lam_h,
        "lam_away": lam_a,
        "home_win_prob": hw,
        "draw_prob": draw,
        "away_win_prob": aw,
        "home_clean_sheet_prob": home_cs,
        "away_clean_sheet_prob": away_cs,
        "home_score_prob": predict_score_prob(lam_h),
        "away_score_prob": predict_score_prob(lam_a),
    }


def _fpl_fixture_difficulty(fx: Fixture, team_id: int) -> int | None:
    if fx.home_team_id == team_id:
        return fx.home_difficulty
    if fx.away_team_id == team_id:
        return fx.away_difficulty
    return None


def _raw_difficulty_score(
    fx: Fixture, team_id: int, ratings: dict[int, dict[str, float]]
) -> float:
    outcomes = _fixture_outcomes(fx, ratings)
    is_home = fx.home_team_id == team_id
    if is_home:
        model_score = raw_difficulty_from_lambdas(outcomes["lam_home"], outcomes["lam_away"])
    else:
        model_score = raw_difficulty_from_lambdas(outcomes["lam_away"], outcomes["lam_home"])
    return blend_with_fpl_fdr(model_score, _fpl_fixture_difficulty(fx, team_id))


def _scale_breaks(scale: DifficultyScale) -> tuple[float, float, float, float]:
    return (scale.break_p20, scale.break_p40, scale.break_p60, scale.break_p80)


def _difficulty_for_team(
    fx: Fixture,
    team_id: int,
    ratings: dict[int, dict[str, float]],
    breaks: tuple[float, float, float, float],
) -> tuple[int, float, str]:
    raw = _raw_difficulty_score(fx, team_id, ratings)
    level = level_from_breaks(raw, breaks)
    return level, round(raw, 2), label_for_level(level)


def freeze_weekly_difficulty_scale(
    db: Session,
    start_gw: int,
    *,
    overwrite: bool = False,
    season: Season | None = None,
    teams: dict[int, Team] | None = None,
    ratings: dict[int, dict[str, float]] | None = None,
) -> DifficultyScale | None:
    """Persist 20/40/60/80 cuts for this GW. Reused until the next weekly inference."""
    Base.metadata.create_all(bind=engine, tables=[DifficultyScale.__table__])
    season = season or _current_season(db)
    if not season:
        return None
    existing = (
        db.query(DifficultyScale)
        .filter(
            DifficultyScale.season_id == season.id,
            DifficultyScale.as_of_gameweek == start_gw,
        )
        .first()
    )
    if existing and not overwrite:
        return existing

    teams = teams or _team_map(db, season.id)
    ratings = ratings or _ratings_as_of_gw(db, season, start_gw, teams)
    by_team = _upcoming_fixtures_by_team(db, season.id, start_gw, FDR_SCALE_WINDOW)
    scores: list[float] = []
    for team_id, fixtures in by_team.items():
        for fx in fixtures:
            scores.append(_raw_difficulty_score(fx, team_id, ratings))
    breaks = quantile_breaks(scores)
    score_min = min(scores) if scores else breaks[0]
    score_max = max(scores) if scores else breaks[3]
    if existing:
        existing.break_p20, existing.break_p40, existing.break_p60, existing.break_p80 = breaks
        existing.score_min = score_min
        existing.score_max = score_max
        existing.sample_count = len(scores)
        db.commit()
        db.refresh(existing)
        return existing
    scale = DifficultyScale(
        season_id=season.id,
        as_of_gameweek=start_gw,
        break_p20=breaks[0],
        break_p40=breaks[1],
        break_p60=breaks[2],
        break_p80=breaks[3],
        score_min=score_min,
        score_max=score_max,
        sample_count=len(scores),
    )
    db.add(scale)
    db.commit()
    db.refresh(scale)
    return scale


def _upcoming_fixtures_by_team(
    db: Session, season_id: int, start_gw: int, max_per_team: int
) -> dict[int, list[Fixture]]:
    fixtures = (
        db.query(Fixture)
        .filter(
            Fixture.season_id == season_id,
            Fixture.gameweek_number.isnot(None),
            Fixture.gameweek_number >= start_gw,
            Fixture.finished.is_(False),
        )
        .order_by(Fixture.gameweek_number, Fixture.kickoff_time)
        .all()
    )
    by_team: dict[int, list[Fixture]] = defaultdict(list)
    for fx in fixtures:
        for tid in (fx.home_team_id, fx.away_team_id):
            if len(by_team[tid]) < max_per_team:
                by_team[tid].append(fx)
    return by_team


def team_fixture_runs(db: Session, start_gw: int, fixture_count: int) -> list[dict]:
    season = _current_season(db)
    if not season:
        return []
    teams = _team_map(db, season.id)
    by_team = _upcoming_fixtures_by_team(db, season.id, start_gw, fixture_count)
    ratings = _ratings_as_of_gw(db, season, start_gw, teams)
    scale = freeze_weekly_difficulty_scale(
        db, start_gw, overwrite=False, season=season, teams=teams, ratings=ratings
    )
    breaks = _scale_breaks(scale) if scale else quantile_breaks([])

    rows: list[dict] = []
    for team_id, team in sorted(teams.items(), key=lambda x: x[1].name):
        cells: list[dict] = []
        diff_scores: list[float] = []
        for fx in by_team.get(team_id, []):
            is_home = fx.home_team_id == team_id
            opp_id = fx.away_team_id if is_home else fx.home_team_id
            opp = teams.get(opp_id)
            level, score, label = _difficulty_for_team(fx, team_id, ratings, breaks)
            diff_scores.append(score)
            cells.append(
                {
                    "gameweek_number": fx.gameweek_number,
                    "opponent_short": opp.short_name if opp else "?",
                    "is_home": is_home,
                    "fdr": level,
                    "difficulty_level": level,
                    "difficulty_label": label,
                    "difficulty_score": score,
                }
            )
        if not cells:
            continue
        avg_diff = sum(diff_scores) / len(diff_scores)
        overall_level = level_from_breaks(avg_diff, breaks)
        rows.append(
            {
                "team_id": team_id,
                "team_name": team.name,
                "short_name": team.short_name,
                "team_code": team.code,
                "overall_fdr": round(avg_diff, 2),
                "overall_difficulty_level": overall_level,
                "overall_difficulty_label": label_for_level(overall_level),
                "fixtures": cells,
                "difficulty_model": STRENGTH_DIFFICULTY_MODEL,
                "fixture_window": fixture_count,
            }
        )
    return rows


def team_clean_sheet_runs(db: Session, start_gw: int, fixture_count: int) -> list[dict]:
    return _team_metric_runs(db, start_gw, fixture_count, "cs")


def team_goals_runs(db: Session, start_gw: int, fixture_count: int) -> list[dict]:
    return _team_metric_runs(db, start_gw, fixture_count, "goals")


def _team_metric_runs(
    db: Session, start_gw: int, fixture_count: int, metric: str
) -> list[dict]:
    season = _current_season(db)
    if not season:
        return []
    teams = _team_map(db, season.id)
    by_team = _upcoming_fixtures_by_team(db, season.id, start_gw, fixture_count)
    ratings = _ratings_as_of_gw(db, season, start_gw, teams)
    gw_numbers = {
        fx.gameweek_number for fixtures in by_team.values() for fx in fixtures if fx.gameweek_number
    }
    pred_map = _prediction_map(db, gw_numbers)
    cs_model = _clean_sheet_model(db, season) if metric == "cs" else None

    rows: list[dict] = []
    for team_id, team in sorted(teams.items(), key=lambda x: x[1].name):
        cells: list[dict] = []
        values: list[float] = []
        tr = ratings.get(team_id, _AVERAGE_PRIOR)
        for fx in by_team.get(team_id, []):
            is_home = fx.home_team_id == team_id
            opp_id = fx.away_team_id if is_home else fx.home_team_id
            opp = teams.get(opp_id)
            pred = pred_map.get((fx.id, fx.gameweek_number)) if fx.gameweek_number else None
            outcomes = _fixture_outcomes(fx, ratings)
            if pred is not None:
                if metric == "cs":
                    value = pred.home_clean_sheet_prob if is_home else pred.away_clean_sheet_prob
                else:
                    value = pred.home_score_prob if is_home else pred.away_score_prob
            else:
                if metric == "cs":
                    lam_opp = outcomes["lam_away"] if is_home else outcomes["lam_home"]
                    team_def = tr.get("defense_home" if is_home else "defense_away", 1.0)
                    value = predict_clean_sheet_prob(lam_opp, team_def, is_home, cs_model)
                else:
                    lam_for = outcomes["lam_home"] if is_home else outcomes["lam_away"]
                    value = predict_score_prob(lam_for)
            values.append(value)
            cell: dict = {
                "gameweek_number": fx.gameweek_number,
                "opponent_short": opp.short_name if opp else "?",
                "is_home": is_home,
                "value": round(value, 4),
            }
            if metric == "goals":
                lam_for = outcomes["lam_home"] if is_home else outcomes["lam_away"]
                cell["expected_goals"] = round(lam_for, 2)
            cells.append(cell)
        if not cells:
            continue
        overall = sum(values) / len(values)
        row: dict = {
            "team_id": team_id,
            "team_name": team.name,
            "short_name": team.short_name,
            "team_code": team.code,
            "fixtures": cells,
            "gameweeks_covered": len(cells),
        }
        if metric == "cs":
            row["avg_clean_sheet_prob"] = round(overall, 4)
        else:
            row["avg_score_prob"] = round(overall, 4)
        rows.append(row)

    if metric == "cs":
        return sorted(rows, key=lambda r: -r["avg_clean_sheet_prob"])
    return sorted(rows, key=lambda r: -r["avg_score_prob"])


def team_clean_sheet_outlook(
    db: Session, start_gw: int, gameweek_count: int
) -> list[dict]:
    season = _current_season(db)
    if not season:
        return []
    teams = _team_map(db, season.id)
    end_gw = start_gw + gameweek_count - 1
    gw_range = set(range(start_gw, end_gw + 1))
    preds = (
        db.query(PredictionTeamFixture)
        .filter(PredictionTeamFixture.gameweek_number.in_(gw_range))
        .all()
    )
    if not preds:
        return []
    fixture_ids = [p.fixture_id for p in preds]
    fixtures = {f.id: f for f in db.query(Fixture).filter(Fixture.id.in_(fixture_ids)).all()}
    cs_by_team: dict[int, list[float]] = defaultdict(list)

    for p in preds:
        fx = fixtures.get(p.fixture_id)
        if not fx:
            continue
        cs_by_team[fx.home_team_id].append(p.home_clean_sheet_prob)
        cs_by_team[fx.away_team_id].append(p.away_clean_sheet_prob)

    rows: list[dict] = []
    for team_id, probs in cs_by_team.items():
        team = teams.get(team_id)
        if not team or not probs:
            continue
        avg = sum(probs) / len(probs)
        rows.append(
            {
                "team_id": team_id,
                "team_name": team.name,
                "short_name": team.short_name,
                "avg_clean_sheet_prob": round(avg, 4),
                "gameweeks_covered": len(probs),
            }
        )
    return sorted(rows, key=lambda r: -r["avg_clean_sheet_prob"])


def team_goals_outlook(db: Session, start_gw: int, gameweek_count: int) -> list[dict]:
    season = _current_season(db)
    if not season:
        return []
    teams = _team_map(db, season.id)
    end_gw = start_gw + gameweek_count - 1
    gw_range = set(range(start_gw, end_gw + 1))
    preds = (
        db.query(PredictionTeamFixture)
        .filter(PredictionTeamFixture.gameweek_number.in_(gw_range))
        .all()
    )
    if not preds:
        return []
    fixture_ids = [p.fixture_id for p in preds]
    fixtures = {f.id: f for f in db.query(Fixture).filter(Fixture.id.in_(fixture_ids)).all()}
    goals_by_team: dict[int, list[float]] = defaultdict(list)

    for p in preds:
        fx = fixtures.get(p.fixture_id)
        if not fx:
            continue
        goals_by_team[fx.home_team_id].append(p.home_score_prob)
        goals_by_team[fx.away_team_id].append(p.away_score_prob)

    rows: list[dict] = []
    for team_id, probs in goals_by_team.items():
        team = teams.get(team_id)
        if not team or not probs:
            continue
        avg = sum(probs) / len(probs)
        rows.append(
            {
                "team_id": team_id,
                "team_name": team.name,
                "short_name": team.short_name,
                "avg_score_prob": round(avg, 4),
                "gameweeks_covered": len(probs),
            }
        )
    return sorted(rows, key=lambda r: -r["avg_score_prob"])


def captain_picks(db: Session, gameweek: int, limit: int = 15) -> list[dict]:
    preds = (
        db.query(PredictionPlayerGameweek)
        .filter(PredictionPlayerGameweek.gameweek_number == gameweek)
        .order_by(PredictionPlayerGameweek.expected_points.desc())
        .limit(limit * 2)
        .all()
    )
    if not preds:
        return []
    player_ids = [p.player_id for p in preds]
    players = {pl.id: pl for pl in db.query(Player).filter(Player.id.in_(player_ids)).all()}
    team_ids = {pl.team_id for pl in players.values() if pl.team_id}
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    rows: list[dict] = []
    for p in preds:
        pl = players.get(p.player_id)
        if not pl:
            continue
        team = teams.get(pl.team_id) if pl.team_id else None
        captain_xp = p.expected_points * 2
        rows.append(
            {
                "player_id": pl.id,
                "web_name": pl.web_name,
                "full_name": _full_name(pl),
                **_team_display(team),
                "position": pl.position,
                "expected_points": p.expected_points,
                "captain_expected_points": round(captain_xp, 2),
                "ownership_pct": pl.selected_by_percent,
            }
        )
    rows.sort(key=lambda r: -r["captain_expected_points"])
    return rows[:limit]


def defensive_contribution_outlook(db: Session, gameweek: int, limit: int = 20) -> list[dict]:
    """Estimate likelihood of hitting FPL defensive contribution thresholds (no raw CBIT in DB)."""
    season = _current_season(db)
    if not season:
        return []
    players = (
        db.query(Player)
        .filter(Player.season_id == season.id, Player.position.in_(["DEF", "MID"]))
        .all()
    )
    if not players:
        return []
    player_ids = [p.id for p in players]
    stats = (
        db.query(PlayerGameweekStat)
        .filter(
            PlayerGameweekStat.season_id == season.id,
            PlayerGameweekStat.player_id.in_(player_ids),
            PlayerGameweekStat.gameweek_number < gameweek,
        )
        .all()
    )
    by_player: dict[int, list[PlayerGameweekStat]] = defaultdict(list)
    for s in stats:
        if s.player_id:
            by_player[s.player_id].append(s)

    team_ids = {p.team_id for p in players if p.team_id}
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    cs_rows = {r["team_id"]: r["avg_clean_sheet_prob"] for r in team_clean_sheet_outlook(db, gameweek, 1)}

    rows: list[dict] = []
    for pl in players:
        history = sorted(by_player.get(pl.id, []), key=lambda x: x.gameweek_number)
        if not history:
            continue
        last3 = history[-3:]
        avg_min = sum(x.minutes for x in last3) / len(last3)
        if avg_min < 45:
            continue
        threshold = 10 if pl.position == "DEF" else 12
        minutes_factor = min(1.0, avg_min / 90.0)
        ict_factor = min(1.0, sum(x.ict_index for x in last3) / len(last3) / 30.0)
        team_cs = cs_rows.get(pl.team_id or 0, 0.15)
        pos_boost = 0.15 if pl.position == "DEF" else 0.05
        likelihood = min(0.95, minutes_factor * 0.55 + ict_factor * 0.25 + team_cs * 0.15 + pos_boost)
        team = teams.get(pl.team_id) if pl.team_id else None
        rows.append(
            {
                "player_id": pl.id,
                "web_name": pl.web_name,
                "full_name": _full_name(pl),
                **_team_display(team),
                "position": pl.position,
                "threshold": threshold,
                "likelihood": round(likelihood, 3),
                "avg_minutes_last3": round(avg_min, 1),
            }
        )
    rows.sort(key=lambda r: -r["likelihood"])
    return rows[:limit]


def bonus_points_outlook(db: Session, gameweek: int, limit: int = 20) -> list[dict]:
    season = _current_season(db)
    if not season:
        return []
    prev_gw = max(1, gameweek - 1)
    stats = (
        db.query(PlayerGameweekStat)
        .filter(
            PlayerGameweekStat.season_id == season.id,
            PlayerGameweekStat.gameweek_number == prev_gw,
        )
        .order_by(PlayerGameweekStat.bps.desc())
        .limit(200)
        .all()
    )
    if not stats:
        return []
    player_ids = [s.player_id for s in stats if s.player_id]
    players = {p.id: p for p in db.query(Player).filter(Player.id.in_(player_ids)).all()}
    preds = {
        p.player_id: p
        for p in db.query(PredictionPlayerGameweek)
        .filter(PredictionPlayerGameweek.gameweek_number == gameweek)
        .all()
    }
    team_ids = {p.team_id for p in players.values() if p.team_id}
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    rows: list[dict] = []
    for s in stats:
        if not s.player_id:
            continue
        pl = players.get(s.player_id)
        if not pl:
            continue
        pred = preds.get(pl.id)
        xpts = pred.expected_points if pred else 0.0
        bonus_score = (s.bps / 100.0) * 0.5 + (xpts / 10.0) * 0.35 + (s.ict_index / 50.0) * 0.15
        team = teams.get(pl.team_id) if pl.team_id else None
        rows.append(
            {
                "player_id": pl.id,
                "web_name": pl.web_name,
                "full_name": _full_name(pl),
                **_team_display(team),
                "position": pl.position,
                "last_gw_bps": s.bps,
                "last_gw_bonus": s.bonus,
                "bonus_outlook_score": round(min(1.0, bonus_score), 3),
            }
        )
    rows.sort(key=lambda r: -r["bonus_outlook_score"])
    return rows[:limit]


def home_dashboard(db: Session, gameweek: int | None) -> dict:
    empty = {
        "last_gameweek": 0,
        "price_risers": [],
        "price_fallers": [],
        "transfers_in": [],
        "transfers_out": [],
        "price_risers_all_time": [],
        "price_fallers_all_time": [],
        "transfers_in_all_time": [],
        "transfers_out_all_time": [],
        "top_last_gameweek": [],
    }
    season = _current_season(db)
    if not season:
        return empty
    players = db.query(Player).filter(Player.season_id == season.id).all()
    risers = sorted(
        [p for p in players if p.cost_change_event > 0],
        key=lambda p: -p.cost_change_event,
    )[:10]
    fallers = sorted(
        [p for p in players if p.cost_change_event < 0],
        key=lambda p: p.cost_change_event,
    )[:10]
    transfers_in = sorted(players, key=lambda p: -p.transfers_in_event)[:10]
    transfers_out = sorted(players, key=lambda p: -p.transfers_out_event)[:10]
    risers_all = sorted(
        [p for p in players if p.cost_change_start > 0],
        key=lambda p: -p.cost_change_start,
    )[:10]
    fallers_all = sorted(
        [p for p in players if p.cost_change_start < 0],
        key=lambda p: p.cost_change_start,
    )[:10]
    transfers_in_all = sorted(players, key=lambda p: -p.transfers_in)[:10]
    transfers_out_all = sorted(players, key=lambda p: -p.transfers_out)[:10]

    team_ids = {p.team_id for p in players if p.team_id}
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    def _player_brief(p: Player) -> dict:
        team = teams.get(p.team_id) if p.team_id else None
        return {
            "player_id": p.id,
            "web_name": p.web_name,
            "full_name": _full_name(p),
            **_team_display(team),
            "position": p.position,
            "price": p.now_cost / 10.0,
            "cost_change_event": p.cost_change_event / 10.0,
            "cost_change_start": p.cost_change_start / 10.0,
            "transfers_in_event": p.transfers_in_event,
            "transfers_out_event": p.transfers_out_event,
            "transfers_in": p.transfers_in,
            "transfers_out": p.transfers_out,
            "selected_by_percent": p.selected_by_percent,
        }

    from fpl_shared.models import Gameweek

    finished_gw = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.finished.is_(True))
        .order_by(Gameweek.number.desc())
        .first()
    )
    last_gw = finished_gw.number if finished_gw else 1
    if gameweek is not None:
        requested = (
            db.query(Gameweek)
            .filter(Gameweek.season_id == season.id, Gameweek.number == gameweek)
            .first()
        )
        if requested and requested.finished:
            last_gw = gameweek

    top_stats = (
        db.query(PlayerGameweekStat)
        .filter(
            PlayerGameweekStat.season_id == season.id,
            PlayerGameweekStat.gameweek_number == last_gw,
        )
        .order_by(PlayerGameweekStat.total_points.desc())
        .limit(15)
        .all()
    )
    top_last: list[dict] = []
    for s in top_stats:
        pl = db.query(Player).filter(Player.id == s.player_id).first() if s.player_id else None
        if not pl and s.fpl_element_id:
            pl = (
                db.query(Player)
                .filter(
                    Player.season_id == season.id,
                    Player.fpl_element_id == s.fpl_element_id,
                )
                .first()
            )
        if not pl:
            continue
        team = teams.get(pl.team_id) if pl.team_id else None
        top_last.append(
            {
                "player_id": pl.id,
                "web_name": pl.web_name,
                **_team_display(team),
                "position": pl.position,
                "gameweek_number": last_gw,
                "total_points": s.total_points,
                "goals": s.goals_scored,
                "assists": s.assists,
                "bonus": s.bonus,
            }
        )

    return {
        "last_gameweek": last_gw,
        "price_risers": [_player_brief(p) for p in risers],
        "price_fallers": [_player_brief(p) for p in fallers],
        "transfers_in": [_player_brief(p) for p in transfers_in],
        "transfers_out": [_player_brief(p) for p in transfers_out],
        "price_risers_all_time": [_player_brief(p) for p in risers_all],
        "price_fallers_all_time": [_player_brief(p) for p in fallers_all],
        "transfers_in_all_time": [_player_brief(p) for p in transfers_in_all],
        "transfers_out_all_time": [_player_brief(p) for p in transfers_out_all],
        "top_last_gameweek": top_last,
    }


def player_season_stats(
    db: Session,
    gameweek: int | None,
    position: str | None,
    min_minutes: int,
    limit: int,
) -> list[dict]:
    season = _current_season(db)
    if not season:
        return []
    q = db.query(Player).filter(Player.season_id == season.id)
    if position:
        q = q.filter(Player.position == position.upper())
    players = q.all()
    if not players:
        return []

    stats_q = db.query(PlayerGameweekStat).filter(PlayerGameweekStat.season_id == season.id)
    if gameweek is not None:
        stats_q = stats_q.filter(PlayerGameweekStat.gameweek_number <= gameweek)
    stats = stats_q.all()
    agg: dict[int, dict] = defaultdict(
        lambda: {
            "minutes": 0,
            "points": 0,
            "goals": 0,
            "assists": 0,
            "bonus": 0,
            "bps": 0,
            "xg": 0.0,
            "xa": 0.0,
            "gws": 0,
        }
    )
    for s in stats:
        pid = s.player_id
        if not pid:
            continue
        bucket = agg[pid]
        bucket["minutes"] += s.minutes
        bucket["points"] += s.total_points
        bucket["goals"] += s.goals_scored
        bucket["assists"] += s.assists
        bucket["bonus"] += s.bonus
        bucket["bps"] += s.bps
        bucket["xg"] += s.expected_goals
        bucket["xa"] += s.expected_assists
        bucket["gws"] += 1

    team_ids = {p.team_id for p in players if p.team_id}
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    rows: list[dict] = []
    for pl in players:
        a = agg.get(pl.id)
        if not a or a["minutes"] < min_minutes:
            continue
        team = teams.get(pl.team_id) if pl.team_id else None
        rows.append(
            {
                "player_id": pl.id,
                "web_name": pl.web_name,
                "full_name": _full_name(pl),
                **_team_display(team),
                "position": pl.position,
                "price": pl.now_cost / 10.0,
                "minutes": a["minutes"],
                "total_points": a["points"],
                "goals": a["goals"],
                "assists": a["assists"],
                "bonus": a["bonus"],
                "bps": a["bps"],
                "expected_goals": round(a["xg"], 2),
                "expected_assists": round(a["xa"], 2),
                "gameweeks_played": a["gws"],
            }
        )
    rows.sort(key=lambda r: -r["total_points"])
    return rows[:limit]


def next_deadline(db: Session) -> datetime | None:
    season = _current_season(db)
    if not season:
        return None
    from fpl_shared.models import Gameweek

    nxt = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.is_next.is_(True))
        .first()
    )
    if nxt and nxt.deadline_time:
        return nxt.deadline_time
    open_gw = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.finished.is_(False))
        .order_by(Gameweek.number)
        .first()
    )
    return open_gw.deadline_time if open_gw else None


def _full_name(pl: Player) -> str:
    if pl.first_name and pl.second_name:
        return f"{pl.first_name} {pl.second_name}".strip()
    return pl.web_name
