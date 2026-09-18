from types import SimpleNamespace

from app.squad_analysis import (
    SquadPlayer,
    can_add_club,
    match_player_name,
    pick_best_xi,
    score_rating,
    suggest_transfers,
)


def _sp(**kwargs) -> SquadPlayer:
    defaults = dict(
        player_id=1,
        fpl_element_id=1,
        web_name="A",
        full_name="A A",
        team="MCI",
        team_name="Man City",
        team_code=43,
        team_id=1,
        position="MID",
        price=8.0,
        expected_points=5.0,
        n_fixtures=1,
        opponents="BUR (H)",
        opp_fdr=2.0,
    )
    defaults.update(kwargs)
    return SquadPlayer(**defaults)


def test_pick_best_xi_uses_legal_formation():
    squad = (
        [_sp(player_id=i, fpl_element_id=i, position="GK", expected_points=4 - i * 0.1, team_id=10 + i) for i in range(2)]
        + [_sp(player_id=10 + i, fpl_element_id=10 + i, position="DEF", expected_points=5 - i * 0.2, team_id=20 + i) for i in range(5)]
        + [_sp(player_id=20 + i, fpl_element_id=20 + i, position="MID", expected_points=6 - i * 0.2, team_id=30 + i) for i in range(5)]
        + [_sp(player_id=30 + i, fpl_element_id=30 + i, position="FWD", expected_points=7 - i * 0.3, team_id=40 + i) for i in range(3)]
    )
    xi, score, shape = pick_best_xi(squad)
    assert len(xi) == 11
    assert sum(shape.values()) == 11
    assert shape["GK"] == 1
    assert score > 0
    by_pos = {pos: sum(1 for p in xi if p.position == pos) for pos in ("GK", "DEF", "MID", "FWD")}
    assert by_pos == shape


def test_rating_is_bounded_and_rises_with_better_xi():
    low, low_label = score_rating(30, 55, 4, 8, 4.2, 4)
    high, high_label = score_rating(54, 55, 7.5, 8, 2.4, 0)
    assert 1 <= low <= 99
    assert 1 <= high <= 99
    assert high > low
    assert high_label in {"strong", "solid"}
    assert low_label in {"mixed", "needs work"}


def test_transfer_respects_budget_and_three_per_club():
    squad = []
    squad += [
        _sp(
            player_id=100 + i,
            fpl_element_id=100 + i,
            position="GK",
            expected_points=4,
            price=4.5,
            team_id=50 + i,
            web_name=f"GK{i}",
        )
        for i in range(2)
    ]
    squad.append(
        _sp(
            player_id=1,
            fpl_element_id=1,
            position="DEF",
            price=4.5,
            expected_points=1.5,
            team_id=1,
            web_name="Weak",
        )
    )
    squad += [
        _sp(
            player_id=201 + i,
            fpl_element_id=201 + i,
            position="DEF",
            expected_points=4.8,
            price=4.5,
            team_id=62 + i,
            web_name=f"DEF{i}",
        )
        for i in range(4)
    ]
    squad += [
        _sp(
            player_id=300 + i,
            fpl_element_id=300 + i,
            position="MID",
            expected_points=5.0,
            price=6.0,
            team_id=60 if i < 3 else 70 + i,
            web_name=f"MID{i}",
        )
        for i in range(5)
    ]
    squad += [
        _sp(
            player_id=400 + i,
            fpl_element_id=400 + i,
            position="FWD",
            expected_points=6.0,
            price=8.0,
            team_id=80 + i,
            web_name=f"FWD{i}",
        )
        for i in range(3)
    ]

    too_expensive = _sp(
        player_id=9,
        fpl_element_id=9,
        position="DEF",
        price=14.0,
        expected_points=9.0,
        team_id=99,
        web_name="Haaland",
    )
    club_blocked = _sp(
        player_id=10,
        fpl_element_id=10,
        position="DEF",
        price=4.8,
        expected_points=8.0,
        team_id=60,
        web_name="Blocked",
    )
    good = _sp(
        player_id=11,
        fpl_element_id=11,
        position="DEF",
        price=4.7,
        expected_points=6.5,
        team_id=88,
        web_name="Saka",
    )
    cards = suggest_transfers(squad, [too_expensive, club_blocked, good], bank=0.5, limit=3)
    names = [c["in"]["web_name"] for c in cards]
    assert "Saka" in names
    assert "Haaland" not in names
    assert "Blocked" not in names
    assert all(c["gain"] > 0 for c in cards)


def test_match_player_name_exact_and_fuzzy():
    players = [
        SimpleNamespace(
            id=1,
            web_name="Haaland",
            first_name="Erling",
            second_name="Haaland",
        ),
        SimpleNamespace(
            id=2,
            web_name="B.Fernandes",
            first_name="Bruno",
            second_name="Fernandes",
        ),
    ]
    hit, score = match_player_name("Haaland", players, set())
    assert hit.id == 1 and score == 1.0
    hit2, score2 = match_player_name("Bruno Fernandes", players, set())
    assert hit2.id == 2 and score2 >= 0.72
    miss, _ = match_player_name("Nobody", players, set())
    assert miss is None


def test_match_joao_pedro_not_costinha():
    costinha = SimpleNamespace(
        id=10,
        web_name="Costinha",
        first_name="João Pedro",
        second_name="Loureiro da Costa",
        position="DEF",
    )
    joao = SimpleNamespace(
        id=11,
        web_name="João Pedro",
        first_name="João Pedro",
        second_name="Junqueira de Jesus",
        position="FWD",
    )
    players = [costinha, joao]
    hit, score = match_player_name("Joao Pedro", players, set())
    assert hit.id == 11 and score >= 0.99
    hit_pos, _ = match_player_name("João Pedro", players, set(), position="FWD")
    assert hit_pos.id == 11
    nick, _ = match_player_name("Costinha", players, set())
    assert nick.id == 10


def test_can_add_club_enforces_three():
    squad = [
        _sp(player_id=i, team_id=1) for i in range(3)
    ]
    assert can_add_club(squad, 1) is False
    assert can_add_club(squad, 1, removing=1) is True
    assert can_add_club(squad, 2) is True
