"""Bulk helpers so historical ETL does not round-trip Neon once per row."""

from __future__ import annotations

from sqlalchemy.orm import Session

from fpl_shared.models import Fixture, Gameweek, Player, PlayerGameweekStat, Team

INSERT_CHUNK = 2000


def existing_player_gw_keys(db: Session, season_id: int) -> set[tuple[int, int]]:
    rows = (
        db.query(PlayerGameweekStat.fpl_element_id, PlayerGameweekStat.gameweek_number)
        .filter(PlayerGameweekStat.season_id == season_id)
        .all()
    )
    return {(int(element_id), int(gw)) for element_id, gw in rows}


def players_by_element(db: Session, season_id: int) -> dict[int, Player]:
    return {
        p.fpl_element_id: p
        for p in db.query(Player).filter(Player.season_id == season_id).all()
        if p.fpl_element_id
    }


def teams_by_fpl_id(db: Session, season_id: int) -> dict[int, Team]:
    return {t.fpl_team_id: t for t in db.query(Team).filter(Team.season_id == season_id).all()}


def gameweeks_by_number(db: Session, season_id: int) -> dict[int, Gameweek]:
    return {gw.number: gw for gw in db.query(Gameweek).filter(Gameweek.season_id == season_id).all()}


def fixture_ids(db: Session, season_id: int) -> set[int]:
    rows = db.query(Fixture.fpl_fixture_id).filter(Fixture.season_id == season_id).all()
    return {int(fid) for (fid,) in rows}


def flush_player_gw_rows(db: Session, rows: list[dict], chunk: int = INSERT_CHUNK) -> int:
    if not rows:
        return 0
    total = 0
    for start in range(0, len(rows), chunk):
        batch = rows[start : start + chunk]
        db.bulk_insert_mappings(PlayerGameweekStat, batch)
        db.commit()
        total += len(batch)
        print(f"  inserted {total} player-gameweek rows...", flush=True)
    return total
