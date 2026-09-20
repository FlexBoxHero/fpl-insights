from app.player_watch import parse_return_date, price_outlook


def test_parse_return_date_expected_back():
    assert parse_return_date("Knee injury - Expected back 10 Oct") == "10 Oct"


def test_parse_return_date_suspended_until():
    assert parse_return_date("Suspended until 19 Oct") == "19 Oct"


def test_parse_return_date_unknown():
    assert parse_return_date("Back injury - Unknown return date") == "Unknown"


def test_parse_return_date_missing():
    assert parse_return_date("Hamstring injury - 75% chance of playing") is None
    assert parse_return_date("") is None
    assert parse_return_date(None) is None


def test_price_outlook_likelihood_and_percent_fallback():
    assert price_outlook(5, 40) == ("Very likely to rise", "rise")
    assert price_outlook(-3, 10) == ("Likely to drop", "drop")
    assert price_outlook(None, 109.4) == ("Very likely to rise", "rise")
    assert price_outlook(None, -125.7) == ("Very likely to drop", "drop")
    assert price_outlook(None, 12) == ("Unlikely to change", "neutral")


def test_player_watch_schema_includes_selected_not_vice():
    from app.schemas import PlayerWatchOut

    fields = PlayerWatchOut.model_fields
    assert "most_selected" in fields
    assert "most_captained" in fields
    assert "captain_sample_size" in fields
    from app.schemas import CaptainedRowOut

    assert "captain_pct" in CaptainedRowOut.model_fields


def test_captain_rows_use_sample_percent_not_ownership():
    from app.player_watch import captain_rows_from_counts

    haaland = {
        "id": 1,
        "web_name": "Haaland",
        "first_name": "Erling",
        "second_name": "Haaland",
        "team": 11,
        "element_type": 4,
        "now_cost": 145,
        "selected_by_percent": "73.4",
    }
    palmer = {
        "id": 2,
        "web_name": "Palmer",
        "first_name": "Cole",
        "second_name": "Palmer",
        "team": 8,
        "element_type": 3,
        "now_cost": 105,
        "selected_by_percent": "40.0",
    }
    teams = {
        11: {"short_name": "MCI", "name": "Man City", "code": 43},
        8: {"short_name": "CHE", "name": "Chelsea", "code": 8},
    }
    rows = captain_rows_from_counts(
        {1: 35, 2: 8},
        50,
        {1: haaland, 2: palmer},
        {},
        {},
        {},
        teams,
        official_id=1,
    )
    assert [r["web_name"] for r in rows] == ["Haaland", "Palmer"]
    assert rows[0]["captain_pct"] == 70.0
    assert rows[1]["captain_pct"] == 16.0
    assert rows[0]["ownership_pct"] == 73.4
    assert rows[0]["badge"] == "Most captained"
    assert rows[1]["badge"] == "Captain pick"

