"""Sync current season from the official FPL API."""

from __future__ import annotations

from datetime import datetime, timezone

from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from fpl_shared.fpl_client import FplClient
from fpl_shared.models import Fixture, Gameweek, Player, Season, Team

ELEMENT_TYPE_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _current_season_code(events: list[dict]) -> str:
    if not events:
        return datetime.now(timezone.utc).strftime("%Y") + "-" + str(int(datetime.now().year) + 1)[-2:]
    first = events[0].get("deadline_time") or ""
    try:
        year = date_parser.isoparse(first).year
    except (ValueError, TypeError):
        year = datetime.now(timezone.utc).year
    return f"{year}-{str(year + 1)[-2:]}"


def sync_current_season_from_api(db: Session) -> dict[str, int | str]:
    client = FplClient()
    try:
        bootstrap = client.bootstrap_static()
        fixtures_data = client.fixtures()
    finally:
        client.close()

    events = bootstrap.get("events", [])
    season_code = _current_season_code(events)
    season = db.query(Season).filter(Season.code == season_code).first()
    if not season:
        season = Season(code=season_code, is_current=True)
        db.add(season)
        db.commit()
        db.refresh(season)
    else:
        season.is_current = True
        db.query(Season).filter(Season.id != season.id).update({"is_current": False})
        db.commit()

    team_by_fpl: dict[int, Team] = {}
    for t in bootstrap.get("teams", []):
        fpl_id = int(t["id"])
        team = (
            db.query(Team).filter(Team.season_id == season.id, Team.fpl_team_id == fpl_id).first()
        )
        if not team:
            team = Team(
                season_id=season.id,
                fpl_team_id=fpl_id,
                name=t["name"],
                short_name=t["short_name"],
                code=t.get("code"),
            )
            db.add(team)
            db.flush()
        else:
            team.name = t["name"]
            team.short_name = t["short_name"]
        team_by_fpl[fpl_id] = team
    db.commit()

    gw_map: dict[int, Gameweek] = {}
    for ev in events:
        num = int(ev["id"])
        gw = (
            db.query(Gameweek)
            .filter(Gameweek.season_id == season.id, Gameweek.number == num)
            .first()
        )
        deadline = None
        if ev.get("deadline_time"):
            try:
                deadline = date_parser.isoparse(ev["deadline_time"])
            except (ValueError, TypeError):
                deadline = None
        if not gw:
            gw = Gameweek(
                season_id=season.id,
                number=num,
                name=ev.get("name", f"Gameweek {num}"),
                deadline_time=deadline,
                finished=bool(ev.get("finished")),
                is_current=bool(ev.get("is_current")),
                is_next=bool(ev.get("is_next")),
            )
            db.add(gw)
            db.flush()
        else:
            gw.deadline_time = deadline
            gw.finished = bool(ev.get("finished"))
            gw.is_current = bool(ev.get("is_current"))
            gw.is_next = bool(ev.get("is_next"))
        gw_map[num] = gw
    db.commit()

    player_count = 0
    for el in bootstrap.get("elements", []):
        element_id = int(el["id"])
        team = team_by_fpl.get(int(el["team"]))
        position = ELEMENT_TYPE_MAP.get(int(el["element_type"]), "MID")
        player = (
            db.query(Player)
            .filter(Player.season_id == season.id, Player.fpl_element_id == element_id)
            .first()
        )
        if not player:
            player = Player(
                season_id=season.id,
                fpl_element_id=element_id,
                team_id=team.id if team else None,
                web_name=el["web_name"],
                first_name=el.get("first_name"),
                second_name=el.get("second_name"),
                position=position,
                now_cost=int(el.get("now_cost", 0)),
                selected_by_percent=float(el.get("selected_by_percent", 0)),
                ep_next=float(el["ep_next"]) if el.get("ep_next") is not None else None,
                form=float(el["form"]) if el.get("form") is not None else None,
                transfers_in_event=int(el.get("transfers_in_event", 0)),
                transfers_out_event=int(el.get("transfers_out_event", 0)),
                transfers_in=int(el.get("transfers_in", 0)),
                transfers_out=int(el.get("transfers_out", 0)),
                cost_change_event=int(el.get("cost_change_event", 0)),
                cost_change_start=int(el.get("cost_change_start", 0)),
            )
            db.add(player)
        else:
            player.team_id = team.id if team else None
            player.web_name = el["web_name"]
            player.first_name = el.get("first_name")
            player.second_name = el.get("second_name")
            player.position = position
            player.now_cost = int(el.get("now_cost", 0))
            player.selected_by_percent = float(el.get("selected_by_percent", 0))
            player.ep_next = float(el["ep_next"]) if el.get("ep_next") is not None else None
            player.form = float(el["form"]) if el.get("form") is not None else None
            player.transfers_in_event = int(el.get("transfers_in_event", 0))
            player.transfers_out_event = int(el.get("transfers_out_event", 0))
            player.transfers_in = int(el.get("transfers_in", 0))
            player.transfers_out = int(el.get("transfers_out", 0))
            player.cost_change_event = int(el.get("cost_change_event", 0))
            player.cost_change_start = int(el.get("cost_change_start", 0))
        player_count += 1
    db.commit()

    fixture_count = 0
    for fx in fixtures_data:
        fpl_fixture_id = int(fx["id"])
        home = team_by_fpl.get(int(fx["team_h"]))
        away = team_by_fpl.get(int(fx["team_a"]))
        if not home or not away:
            continue
        gw_num = int(fx["event"]) if fx.get("event") else None
        gw_obj = gw_map.get(gw_num) if gw_num else None
        kickoff = None
        if fx.get("kickoff_time"):
            try:
                kickoff = date_parser.isoparse(fx["kickoff_time"])
            except (ValueError, TypeError):
                kickoff = None
        fixture = (
            db.query(Fixture)
            .filter(Fixture.season_id == season.id, Fixture.fpl_fixture_id == fpl_fixture_id)
            .first()
        )
        if not fixture:
            fixture = Fixture(
                season_id=season.id,
                fpl_fixture_id=fpl_fixture_id,
                gameweek_id=gw_obj.id if gw_obj else None,
                gameweek_number=gw_num,
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff_time=kickoff,
                finished=bool(fx.get("finished")),
                home_score=int(fx["team_h_score"]) if fx.get("team_h_score") is not None else None,
                away_score=int(fx["team_a_score"]) if fx.get("team_a_score") is not None else None,
                home_difficulty=int(fx.get("team_h_difficulty", 0)) or None,
                away_difficulty=int(fx.get("team_a_difficulty", 0)) or None,
            )
            db.add(fixture)
        else:
            fixture.gameweek_id = gw_obj.id if gw_obj else None
            fixture.gameweek_number = gw_num
            fixture.kickoff_time = kickoff
            fixture.finished = bool(fx.get("finished"))
            fixture.home_score = (
                int(fx["team_h_score"]) if fx.get("team_h_score") is not None else None
            )
            fixture.away_score = (
                int(fx["team_a_score"]) if fx.get("team_a_score") is not None else None
            )
        fixture_count += 1
    db.commit()

    return {
        "season": season_code,
        "teams": len(team_by_fpl),
        "players": player_count,
        "fixtures": fixture_count,
        "gameweeks": len(gw_map),
    }
