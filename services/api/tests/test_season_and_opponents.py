from types import SimpleNamespace

from app.insights_service import add_gw_to_season, empty_season_bucket, opponent_labels, opponent_summary
from fpl_shared.models import Team


def _team(tid: int, short: str) -> Team:
    team = Team(season_id=1, fpl_team_id=tid, name=short, short_name=short)
    team.id = tid
    return team


def test_opponent_labels_home_and_dgw():
    bur = _team(1, "BUR")
    ars = _team(2, "ARS")
    wol = _team(3, "WOL")
    teams = {1: bur, 2: ars, 3: wol}
    home = SimpleNamespace(home_team_id=2, away_team_id=1)
    away = SimpleNamespace(home_team_id=3, away_team_id=2)
    assert opponent_labels([home], 2, teams) == "BUR (H)"
    assert opponent_labels([home, away], 2, teams) == "BUR (H), WOL (A)"
    assert opponent_labels([], 2, teams) == "Blank"


def test_opponent_summary_single_and_blank():
    bur = _team(1, "BUR")
    ars = _team(2, "ARS")
    teams = {1: bur, 2: ars}
    fx = SimpleNamespace(home_team_id=2, away_team_id=1)
    one = opponent_summary([fx], 2, teams)
    assert one == {"opponents": "BUR (H)", "n_fixtures": 1, "is_home": True}
    blank = opponent_summary([], 2, teams)
    assert blank["opponents"] == "Blank"
    assert blank["n_fixtures"] == 0
    assert blank["is_home"] is None


def test_season_bucket_counts_starts_subs_and_defcon():
    bucket = empty_season_bucket()
    start = SimpleNamespace(
        minutes=90,
        total_points=6,
        goals_scored=1,
        assists=0,
        bonus=1,
        bps=20,
        expected_goals=0.4,
        expected_assists=0.1,
        expected_goals_conceded=0.8,
        starts=1,
        clean_sheets=1,
        goals_conceded=0,
        ict_index=8.2,
        clearances_blocks_interceptions=5,
        tackles=2,
        recoveries=3,
        defensive_contribution=2,
    )
    sub = SimpleNamespace(
        minutes=20,
        total_points=1,
        goals_scored=0,
        assists=0,
        bonus=0,
        bps=4,
        expected_goals=0.0,
        expected_assists=0.0,
        expected_goals_conceded=0.2,
        starts=0,
        clean_sheets=0,
        goals_conceded=1,
        ict_index=1.1,
        clearances_blocks_interceptions=1,
        tackles=0,
        recoveries=1,
        defensive_contribution=0,
    )
    add_gw_to_season(bucket, start)
    add_gw_to_season(bucket, sub)
    assert bucket["starts"] == 1
    assert bucket["subbed_in"] == 1
    assert bucket["clean_sheets"] == 1
    assert bucket["goals_conceded"] == 1
    assert abs(bucket["xgc"] - 1.0) < 1e-9
    assert bucket["cbi"] == 6
    assert bucket["tackles"] == 2
    assert bucket["recoveries"] == 4
    assert bucket["defcon"] == 2


def _xi_player(pid: int, name: str, pos: str, points: int, team_id: int) -> dict:
    return {
        "player_id": pid,
        "web_name": name,
        "position": pos,
        "points": points,
        "team_id": team_id,
    }


def test_select_best_xi_picks_highest_legal_shape():
    from app.insights_service import select_best_xi

    players = [
        _xi_player(1, "GK1", "GK", 20, 1),
        _xi_player(2, "GK2", "GK", 4, 2),
        *[_xi_player(10 + i, f"D{i}", "DEF", 12 - i, 3 if i < 3 else 4) for i in range(5)],
        *[_xi_player(20 + i, f"M{i}", "MID", 18 - i, 5 if i < 3 else 6) for i in range(5)],
        _xi_player(30, "F1", "FWD", 25, 7),
        _xi_player(31, "F2", "FWD", 22, 8),
        _xi_player(32, "F3", "FWD", 8, 9),
    ]
    picked, formation, total = select_best_xi(players)
    assert len(picked) == 11
    assert formation == "3-5-2"
    names = {p["web_name"] for p in picked}
    assert "F1" in names and "F2" in names
    assert "F3" not in names
    assert total == sum(p["points"] for p in picked)


def test_select_best_xi_respects_three_per_club():
    from app.insights_service import select_best_xi

    players = [
        _xi_player(1, "GK1", "GK", 10, 1),
        *[_xi_player(10 + i, f"D{i}", "DEF", 20, 1) for i in range(4)],
        _xi_player(20, "Dclub2", "DEF", 6, 2),
        _xi_player(21, "Dclub3", "DEF", 6, 3),
        *[_xi_player(30 + i, f"M{i}", "MID", 10, 4 + i) for i in range(4)],
        _xi_player(40, "F1", "FWD", 10, 8),
        _xi_player(41, "F2", "FWD", 9, 9),
        _xi_player(42, "F3", "FWD", 8, 10),
    ]
    picked, _formation, _total = select_best_xi(players)
    club1 = [p for p in picked if p["team_id"] == 1]
    assert len(club1) <= 3
    assert any(p["web_name"] == "Dclub2" for p in picked)


def test_pick_best_stat_by_gameweek_takes_highest_points():
    from app.insights_service import pick_best_stat_by_gameweek, season_display_label

    stats = [
        SimpleNamespace(gameweek_number=1, total_points=12, player_id=2),
        SimpleNamespace(gameweek_number=1, total_points=17, player_id=9),
        SimpleNamespace(gameweek_number=2, total_points=8, player_id=4),
        SimpleNamespace(gameweek_number=2, total_points=8, player_id=3),
    ]
    best = pick_best_stat_by_gameweek(stats)
    assert best[1].player_id == 9
    assert best[2].player_id == 3
    assert season_display_label("2026-27") == "2026/27"
