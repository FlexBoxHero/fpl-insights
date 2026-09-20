from fpl_ml.defcon import (
    PLAYER_MODEL_DEFCON_COLS,
    action_count,
    as_stat,
    blend_hit_probability,
    defcon_threshold,
    expected_defcon_count,
    expected_defcon_points,
    predicted_defcon_actions,
    feature_row,
    hit_threshold,
    rolling_defcon_features,
    sigmoid_threshold_probability,
)
from fpl_ml.player_model import FEATURE_COLS, rolling_features


def test_def_threshold_is_cbit_10_and_excludes_recoveries():
    near = as_stat(clearances_blocks_interceptions=8, tackles=1, recoveries=20, minutes=90)
    hit = as_stat(clearances_blocks_interceptions=8, tackles=2, recoveries=0, minutes=90)
    assert action_count(near, "DEF") == 9
    assert not hit_threshold(near, "DEF")
    assert hit_threshold(hit, "DEF")
    assert defcon_threshold("DEF") == 10


def test_mid_and_fwd_threshold_is_cbirt_12():
    miss = as_stat(clearances_blocks_interceptions=6, tackles=3, recoveries=2, minutes=90)
    hit = as_stat(clearances_blocks_interceptions=6, tackles=3, recoveries=3, minutes=90)
    assert action_count(miss, "MID") == 11
    assert not hit_threshold(miss, "MID")
    assert hit_threshold(hit, "FWD")
    assert defcon_threshold("MID") == defcon_threshold("FWD") == 12


def test_predicted_defcons_are_cbit_actions_not_awards():
    history = [
        as_stat(clearances_blocks_interceptions=8, tackles=4, recoveries=20, minutes=90)
        for _ in range(3)
    ]
    features = feature_row(history, "DEF")
    assert features is not None
    predicted = predicted_defcon_actions(features)
    assert abs(predicted - 12.0) < 1e-6
    assert predicted != 1.0
    mid = feature_row(history, "MID")
    assert mid is not None
    assert predicted_defcon_actions(mid) > predicted


def test_awarded_defcon_points_do_not_stack():
    stacked = as_stat(defensive_contribution=4, clearances_blocks_interceptions=20, tackles=10)
    assert hit_threshold(stacked, "DEF")
    assert expected_defcon_count(1.0, n_matches=1) == 1.0
    assert expected_defcon_count(0.4, n_matches=2) == 0.8
    assert expected_defcon_points(1.0, n_matches=1) == 2.0
    assert expected_defcon_points(0.4, n_matches=2) == 1.6


def test_sigmoid_is_half_at_threshold_and_rises_past_it():
    at_bar = sigmoid_threshold_probability(10, 10)
    above = sigmoid_threshold_probability(14, 10)
    below = sigmoid_threshold_probability(6, 10)
    assert abs(at_bar - 0.5) < 1e-9
    assert above > at_bar > below


def test_rolling_cbit_and_per90_are_causal():
    history = [
        as_stat(clearances_blocks_interceptions=6, tackles=4, recoveries=8, minutes=90, gameweek_number=1),
        as_stat(clearances_blocks_interceptions=5, tackles=5, recoveries=10, minutes=90, gameweek_number=2),
        as_stat(clearances_blocks_interceptions=4, tackles=2, recoveries=6, minutes=45, gameweek_number=3),
    ]
    feats = rolling_defcon_features(history, "MID")
    assert feats["roll3_cbi"] == (6 + 5 + 4) / 3
    assert feats["roll3_tackles"] == (4 + 5 + 2) / 3
    assert feats["roll3_recoveries"] == (8 + 10 + 6) / 3
    assert feats["roll3_actions"] == (18 + 20 + 12) / 3
    assert abs(feats["roll3_actions_p90"] - (50 / 225 * 90)) < 1e-9


def test_high_cbit_history_beats_low_after_keeping_minutes_ict():
    high = [
        as_stat(
            clearances_blocks_interceptions=9,
            tackles=4,
            minutes=90,
            ict_index=12,
            defensive_contribution=2,
        )
        for _ in range(3)
    ]
    low = [
        as_stat(
            clearances_blocks_interceptions=2,
            tackles=1,
            minutes=90,
            ict_index=12,
            defensive_contribution=0,
        )
        for _ in range(3)
    ]
    features_high = feature_row(high, "DEF")
    features_low = feature_row(low, "DEF")
    assert features_high is not None and features_low is not None
    p_high = blend_hit_probability(features_high, "DEF")
    p_low = blend_hit_probability(features_low, "DEF")
    assert p_high > p_low
    assert expected_defcon_points(p_high) <= 2.0


def test_player_model_keeps_existing_features_and_adds_defcon():
    history = [
        as_stat(
            minutes=90,
            clearances_blocks_interceptions=7,
            tackles=3,
            recoveries=9,
            defensive_contribution=2,
        )
    ]
    feats = rolling_features(history)
    for col in PLAYER_MODEL_DEFCON_COLS:
        assert col in feats
        assert col in FEATURE_COLS
    assert "roll3_points" in FEATURE_COLS
    assert "roll3_minutes" in FEATURE_COLS
    assert feats["roll3_cbit"] == 10
    assert feats["roll3_cbirt"] == 19
