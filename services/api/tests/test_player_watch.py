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
