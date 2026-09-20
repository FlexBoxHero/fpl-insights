from fpl_etl.defcon_fields import defcon_stat_fields
from fpl_etl.gw_stat_fields import extra_gw_stat_fields
from fpl_ml.defcon import (
    as_stat,
    blend_hit_probability,
    expected_defcon_points,
    feature_row,
    predicted_defcon_actions,
)


def test_live_stats_map_combined_cbi_not_split_clearances():
    fields = defcon_stat_fields(
        {
            "clearances_blocks_interceptions": "11",
            "tackles": 3,
            "recoveries": 7,
            "defensive_contribution": 2,
        }
    )
    assert fields["clearances_blocks_interceptions"] == 11
    assert fields["tackles"] == 3
    assert fields["recoveries"] == 7
    assert fields["defensive_contribution"] == 2
    assert "clearances" not in fields


def test_live_stats_map_starts_and_xgc():
    fields = extra_gw_stat_fields(
        {
            "starts": "1",
            "expected_goals_conceded": "0.82",
        }
    )
    assert fields["starts"] == 1
    assert abs(fields["expected_goals_conceded"] - 0.82) < 1e-9
    alias = extra_gw_stat_fields({"starts": 0, "xGC": "1.4"})
    assert alias["starts"] == 0
    assert abs(alias["expected_goals_conceded"] - 1.4) < 1e-9


def test_expected_defcon_is_twice_hit_probability():
    history = [
        as_stat(
            minutes=90,
            clearances_blocks_interceptions=8,
            tackles=4,
            recoveries=2,
            ict_index=10,
            defensive_contribution=2,
        )
        for _ in range(3)
    ]
    features = feature_row(history, "DEF")
    assert features is not None
    predicted = predicted_defcon_actions(features)
    assert abs(predicted - 12.0) < 1e-6
    probability = blend_hit_probability(features, "DEF")
    assert expected_defcon_points(probability) == round(2.0 * probability, 3)
    assert 0.03 <= probability <= 0.95
