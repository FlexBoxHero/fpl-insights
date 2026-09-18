from app.chip_strategy import (
    CaptainPick,
    ChipWindow,
    GwProfile,
    _diversify_tc_windows,
    _scale_xpts,
    assign_plan,
    parse_chips,
    score_bench_boost,
    score_free_hit,
    score_triple_captain,
    score_wildcard,
)


def _profile(**kwargs) -> GwProfile:
    defaults = dict(
        gameweek=8,
        n_matches=10,
        blank_teams=0,
        double_teams=0,
        avg_fdr=3.0,
        easy_fixtures=4,
        template_15_xpts=55.0,
        template_11_xpts=48.0,
        fixture_swing=0.1,
        easy_run_teams=3,
        upcoming_dgw=False,
        top_captain=CaptainPick(
            player_id=1,
            web_name="Haaland",
            full_name="Erling Haaland",
            team="MCI",
            team_name="Man City",
            team_code=43,
            position="FWD",
            expected_points=8.0,
            n_fixtures=1,
            opponents="BUR (H)",
        ),
        half_end=19,
        playable_start=5,
    )
    defaults.update(kwargs)
    return GwProfile(**defaults)


def test_parse_chips_aliases_and_empty():
    assert parse_chips(None) == ["wildcard", "bench_boost", "triple_captain", "free_hit"]
    assert parse_chips("") == []
    assert parse_chips("WC, bb, Triple Captain") == [
        "wildcard",
        "bench_boost",
        "triple_captain",
    ]


def test_triple_captain_prefers_double():
    single = _profile()
    double = _profile(
        top_captain=CaptainPick(
            player_id=1,
            web_name="Haaland",
            full_name="Erling Haaland",
            team="MCI",
            team_name="Man City",
            team_code=43,
            position="FWD",
            expected_points=8.0,
            n_fixtures=2,
            opponents="BUR (H), WOL (A)",
        )
    )
    assert score_triple_captain(double) > score_triple_captain(single)


def test_bench_boost_prefers_doubles_free_hit_prefers_blanks():
    dgw = _profile(gameweek=32, double_teams=8, blank_teams=0, template_15_xpts=80)
    bgw = _profile(gameweek=29, double_teams=0, blank_teams=8, template_11_xpts=52)
    normal = _profile(gameweek=10)
    assert score_bench_boost(dgw) > score_bench_boost(normal)
    assert score_free_hit(bgw) > score_free_hit(dgw)
    assert score_free_hit(bgw) > score_free_hit(normal)


def test_wildcard_prefers_swing_and_avoids_late_half():
    swing = _profile(gameweek=8, fixture_swing=0.4, easy_run_teams=8, upcoming_dgw=True)
    late = _profile(gameweek=19, fixture_swing=0.4, easy_run_teams=8, upcoming_dgw=True)
    assert score_wildcard(swing) > score_wildcard(late)


def test_assign_plan_uses_unique_gameweeks():
    windows = {
        "wildcard": [
            ChipWindow("wildcard", 8, 12, "high", "WC", "rebuild", ()),
            ChipWindow("wildcard", 12, 9, "medium", "WC", "alt", ()),
        ],
        "bench_boost": [
            ChipWindow("bench_boost", 8, 20, "high", "BB", "dgw", ("dgw",)),
            ChipWindow("bench_boost", 16, 11, "medium", "BB", "alt", ()),
        ],
        "triple_captain": [
            ChipWindow("triple_captain", 16, 14, "high", "TC", "haaland", ()),
        ],
        "free_hit": [
            ChipWindow("free_hit", 18, 15, "high", "FH", "blank", ("bgw",)),
        ],
    }
    plan = assign_plan(
        windows, ["wildcard", "bench_boost", "triple_captain", "free_hit"]
    )
    gws = [w.gameweek for w in plan]
    chips = [w.chip for w in plan]
    assert len(gws) == len(set(gws))
    assert set(chips) == {"wildcard", "bench_boost", "triple_captain", "free_hit"}
    by_chip = {w.chip: w.gameweek for w in plan}
    assert by_chip["bench_boost"] == 8
    assert by_chip["wildcard"] < by_chip["bench_boost"] or by_chip["wildcard"] != 8
    assert by_chip["wildcard"] == 12
    assert by_chip["triple_captain"] == 16
    assert by_chip["free_hit"] == 18


def test_scale_xpts_moves_with_fixture_quality():
    base = {"n_fixtures": 1.0, "opp_fdr": 3.0, "is_home": 1.0, "lam_for": 1.6}
    easy_home = {"n_fixtures": 1.0, "opp_fdr": 2.0, "is_home": 1.0, "lam_for": 2.1}
    tough_away = {"n_fixtures": 1.0, "opp_fdr": 4.5, "is_home": 0.0, "lam_for": 0.9}
    easy = _scale_xpts(8.0, base, easy_home)
    tough = _scale_xpts(8.0, base, tough_away)
    assert easy > 8.0
    assert tough < 8.0
    assert easy - tough > 2.5


def test_triple_captain_prefers_juicy_home_fixture():
    bland_away = _profile(
        top_captain=CaptainPick(
            player_id=1,
            web_name="Haaland",
            full_name="Erling Haaland",
            team="MCI",
            team_name="Man City",
            team_code=43,
            position="FWD",
            expected_points=6.0,
            n_fixtures=1,
            opponents="ARS (A)",
            is_home=False,
            expected_goals=1.05,
        )
    )
    juicy_home = _profile(
        gameweek=6,
        top_captain=CaptainPick(
            player_id=2,
            web_name="Salah",
            full_name="Mohamed Salah",
            team="LIV",
            team_name="Liverpool",
            team_code=14,
            position="MID",
            expected_points=6.2,
            n_fixtures=1,
            opponents="BUR (H)",
            is_home=True,
            expected_goals=2.0,
        )
    )
    assert score_triple_captain(juicy_home) > score_triple_captain(bland_away)


def test_diversify_tc_windows_prefers_unique_players():
    haaland_a = CaptainPick(
        player_id=1,
        web_name="Haaland",
        full_name="Erling Haaland",
        team="MCI",
        team_name="Man City",
        team_code=43,
        position="FWD",
        expected_points=8.0,
        n_fixtures=1,
        opponents="BUR (H)",
        is_home=True,
        expected_goals=2.0,
    )
    haaland_b = CaptainPick(
        player_id=1,
        web_name="Haaland",
        full_name="Erling Haaland",
        team="MCI",
        team_name="Man City",
        team_code=43,
        position="FWD",
        expected_points=7.5,
        n_fixtures=1,
        opponents="WOL (A)",
        is_home=False,
        expected_goals=1.4,
    )
    salah = CaptainPick(
        player_id=2,
        web_name="Salah",
        full_name="Mohamed Salah",
        team="LIV",
        team_name="Liverpool",
        team_code=14,
        position="MID",
        expected_points=7.2,
        n_fixtures=1,
        opponents="LEI (H)",
        is_home=True,
        expected_goals=1.9,
    )
    palmer = CaptainPick(
        player_id=3,
        web_name="Palmer",
        full_name="Cole Palmer",
        team="CHE",
        team_name="Chelsea",
        team_code=8,
        position="MID",
        expected_points=6.8,
        n_fixtures=1,
        opponents="SOU (H)",
        is_home=True,
        expected_goals=1.7,
    )
    windows = [
        ChipWindow("triple_captain", 5, 20, "high", "H", "h", (), haaland_a),
        ChipWindow("triple_captain", 8, 18, "high", "H", "h", (), haaland_b),
        ChipWindow("triple_captain", 6, 16, "medium", "S", "s", (), salah),
        ChipWindow("triple_captain", 9, 14, "medium", "P", "p", (), palmer),
    ]
    picked = _diversify_tc_windows(windows, limit=3)
    names = [w.player.web_name for w in picked if w.player]
    assert names == ["Haaland", "Salah", "Palmer"]
    assert [w.gameweek for w in picked] == [5, 6, 9]
