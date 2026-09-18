from types import SimpleNamespace

import numpy as np
import pandas as pd

from fpl_ml.player_model import (
    FEATURE_COLS,
    blend_with_ep_next,
    fixture_context,
    rolling_features,
)
from fpl_ml.team_model import (
    blend_ratings_with_prior,
    _compute_ratings_from_fixtures,
    _expected_goals,
    _outcome_probs,
    clean_sheet_probs,
    predict_clean_sheet_prob,
)


def _fx(home, away, hg, ag, gw, fid=0, hd=3, ad=3):
    return SimpleNamespace(
        finished=True,
        home_score=hg,
        away_score=ag,
        home_team_id=home,
        away_team_id=away,
        gameweek_number=gw,
        id=fid,
        home_difficulty=hd,
        away_difficulty=ad,
    )


def _stat(**kwargs):
    defaults = dict(
        total_points=0,
        minutes=0,
        expected_goals=0.0,
        expected_assists=0.0,
        threat=0.0,
        creativity=0.0,
        bps=0,
        bonus=0,
        goals_scored=0,
        assists=0,
        clean_sheets=0,
        ict_index=0.0,
        gameweek_number=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_clean_sheet_is_poisson_zero_not_one_minus():
    p = predict_clean_sheet_prob(lam_opponent=1.2, team_defense=1.0, is_home=True, cs_model=None)
    poisson_cs = float(np.exp(-1.2))
    inverted = 1.0 - poisson_cs
    assert abs(p - poisson_cs) < abs(p - inverted)
    assert 0.05 <= p <= 0.75


def test_dixon_coles_increases_draw_rate():
    independent = _outcome_probs(1.35, 1.15, rho=0.0)
    dc = _outcome_probs(1.35, 1.15, rho=-0.10)
    assert dc[1] > independent[1]


def test_stronger_home_attack_raises_home_win_and_xG():
    teams = {1: object(), 2: object()}
    fixtures = []
    fid = 1
    for gw in range(1, 9):
        fixtures.append(_fx(1, 2, 3, 0, gw, fid))
        fid += 1
        fixtures.append(_fx(2, 1, 0, 2, gw, fid))
        fid += 1
    ratings = _compute_ratings_from_fixtures(fixtures, teams)
    lam_h, lam_a = _expected_goals(
        ratings[1]["attack_home"],
        ratings[1]["defense_home"],
        ratings[2]["attack_away"],
        ratings[2]["defense_away"],
    )
    hw, _draw, aw = _outcome_probs(lam_h, lam_a)
    assert ratings[1]["attack_home"] > ratings[2]["attack_home"]
    assert ratings[1]["defense_home"] > ratings[2]["defense_home"]
    assert lam_h > lam_a
    assert hw > aw


def test_recency_weights_recent_results_more():
    teams = {1: object(), 2: object(), 3: object(), 4: object()}
    fading = []
    rising = []
    fid = 1
    for gw in range(1, 13):
        fading.append(_fx(1, 3, 4 if gw <= 3 else 0, 0, gw, fid))
        fid += 1
        rising.append(_fx(2, 4, 4 if gw >= 10 else 0, 0, gw, fid))
        fid += 1
    ratings = _compute_ratings_from_fixtures(fading + rising, teams)
    assert ratings[2]["attack_home"] > ratings[1]["attack_home"]


def test_home_and_away_defense_can_differ():
    teams = {1: object(), 2: object()}
    fixtures = []
    fid = 1
    for gw in range(1, 7):
        fixtures.append(_fx(1, 2, 1, 0, gw, fid))  # team 1 concedes 0 at home
        fid += 1
        fixtures.append(_fx(2, 1, 3, 0, gw, fid))  # team 1 concedes 3 away
        fid += 1
    ratings = _compute_ratings_from_fixtures(fixtures, teams)
    assert ratings[1]["defense_home"] > ratings[1]["defense_away"]


def test_clean_sheet_probs_sum_with_score_probs():
    home_cs, away_cs = clean_sheet_probs(1.4, 1.1)
    assert 0.05 < home_cs < 0.7
    assert 0.05 < away_cs < 0.7
    assert abs((1 - away_cs) - (1 - clean_sheet_probs(1.4, 1.1)[1])) < 1e-9


def test_rolling_features_include_xg_xa_and_starts():
    history = [
        _stat(total_points=2, minutes=90, expected_goals=0.4, expected_assists=0.2, threat=20, gameweek_number=1),
        _stat(total_points=6, minutes=90, expected_goals=0.8, expected_assists=0.1, threat=40, gameweek_number=2),
        _stat(total_points=1, minutes=20, expected_goals=0.0, expected_assists=0.0, threat=2, gameweek_number=3),
    ]
    feats = rolling_features(history)
    assert feats["roll3_xgi"] == feats["roll3_xg"] + feats["roll3_xa"]
    assert 0 < feats["start_rate5"] < 1
    assert feats["last_minutes"] == 20
    assert feats["ewm_points"] > 0


def test_fixture_context_sums_double_gameweek_xG():
    player = SimpleNamespace(team_id=1, position="MID")
    fixtures = [
        _fx(1, 2, 0, 0, 8, 1, hd=2, ad=4),
        _fx(3, 1, 0, 0, 8, 2, hd=3, ad=2),
    ]
    ratings = {
        1: {"attack_home": 1.4, "attack_away": 1.2, "defense_home": 1.1, "defense_away": 1.0},
        2: {"attack_home": 0.9, "attack_away": 0.8, "defense_home": 0.9, "defense_away": 0.85},
        3: {"attack_home": 1.3, "attack_away": 1.1, "defense_home": 1.2, "defense_away": 1.05},
    }
    ctx = fixture_context(player, fixtures, ratings)
    single = fixture_context(player, fixtures[:1], ratings)
    assert ctx is not None and single is not None
    assert ctx["n_fixtures"] == 2
    assert ctx["lam_for"] > single["lam_for"]
    assert set(FEATURE_COLS).issuperset({"n_fixtures", "lam_for", "lam_against", "roll3_xa"})


def test_prior_season_keeps_elite_teams_strong_at_gw1():
    teams = {
        1: SimpleNamespace(short_name="MCI"),
        2: SimpleNamespace(short_name="NEW"),
    }
    weak = {
        "attack_home": 0.76,
        "attack_away": 0.72,
        "defense_home": 0.78,
        "defense_away": 0.76,
    }
    current = {1: dict(weak), 2: dict(weak)}
    prior = {
        "MCI": {
            "attack_home": 1.85,
            "attack_away": 1.70,
            "defense_home": 1.80,
            "defense_away": 1.55,
        }
    }
    blended = blend_ratings_with_prior(current, teams, {1: 0, 2: 0}, prior)
    assert blended[1]["attack_home"] > blended[2]["attack_home"]
    later = blend_ratings_with_prior(current, teams, {1: 12, 2: 12}, prior)
    assert later[1]["attack_home"] < blended[1]["attack_home"]


def test_ep_next_blend_moves_toward_official_baseline():
    blended = blend_with_ep_next(np.array([10.0, 2.0]), np.array([4.0, 4.0]))
    assert blended[0] < 10.0
    assert blended[1] > 2.0


def test_ep_next_blend_lifts_premiums_and_trusts_outs():
    premium = blend_with_ep_next(np.array([3.5]), np.array([8.2]))[0]
    assert 5.5 < premium < 8.2
    out = blend_with_ep_next(np.array([2.0]), np.array([0.0]))[0]
    assert out < 0.4


def test_fallback_frame_has_required_feature_columns():
    history = [_stat(total_points=5, minutes=90, expected_goals=0.5, expected_assists=0.3)]
    feats = rolling_features(history)
    player = SimpleNamespace(team_id=1, position="FWD")
    ctx = fixture_context(player, [_fx(1, 2, 0, 0, 4, 1)], {1: {"attack_home": 1, "attack_away": 1, "defense_home": 1, "defense_away": 1}, 2: {"attack_home": 1, "attack_away": 1, "defense_home": 1, "defense_away": 1}})
    row = {**feats, **ctx, "is_gk": 0, "is_def": 0, "is_mid": 0, "is_fwd": 1}
    missing = [c for c in FEATURE_COLS if c not in row]
    assert missing == []
    pd.DataFrame([row])[FEATURE_COLS]


def test_weekly_fdr_quantiles_spread_levels():
    from fpl_ml.difficulty_scale import level_from_breaks, quantile_breaks, raw_difficulty_from_lambdas

    even = raw_difficulty_from_lambdas(1.3, 1.3)
    assert abs(even - 3.0) < 0.15
    easy = raw_difficulty_from_lambdas(2.2, 0.8)
    hard = raw_difficulty_from_lambdas(0.8, 2.2)
    assert easy < even < hard

    scores = [1.6, 2.1, 2.4, 2.7, 3.0, 3.2, 3.5, 3.8, 4.1, 4.6]
    breaks = quantile_breaks(scores)
    levels = [level_from_breaks(s, breaks) for s in scores]
    assert min(levels) == 1
    assert max(levels) == 5
    assert len(set(levels)) >= 4
    assert level_from_breaks(breaks[0], breaks) == (3 if breaks[0] == breaks[3] else 1)


def test_identical_weekly_scores_stay_neutral():
    from fpl_ml.difficulty_scale import level_from_breaks, quantile_breaks

    breaks = quantile_breaks([3.0, 3.0, 3.0, 3.0])
    assert level_from_breaks(3.0, breaks) == 3
