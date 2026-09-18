"""Sync per-GW player stats for the current season from FPL live event data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from fpl_shared.fpl_client import FplClient
from fpl_shared.models import Gameweek, Player, PlayerGameweekStat, Season


def sync_current_season_player_gw_stats(db: Session) -> int:
    season = db.query(Season).filter(Season.is_current.is_(True)).first()
    if not season:
        return 0

    players_by_element = {
        p.fpl_element_id: p for p in db.query(Player).filter(Player.season_id == season.id).all()
    }
    finished_gws = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.finished.is_(True))
        .order_by(Gameweek.number)
        .all()
    )

    client = FplClient()
    inserted = 0
    existing = {
        (s.fpl_element_id, s.gameweek_number): s
        for s in db.query(PlayerGameweekStat).filter(PlayerGameweekStat.season_id == season.id).all()
    }
    try:
        for gw in finished_gws:
            payload = client._get(f"event/{gw.number}/live/")
            for row in payload.get("elements", []):
                element_id = int(row.get("id", 0))
                player = players_by_element.get(element_id)
                if not player:
                    continue
                stats = row.get("stats", row)
                parsed = {
                    "total_points": int(stats.get("total_points", 0)),
                    "minutes": int(stats.get("minutes", 0)),
                    "goals_scored": int(stats.get("goals_scored", 0)),
                    "assists": int(stats.get("assists", 0)),
                    "clean_sheets": int(stats.get("clean_sheets", 0)),
                    "goals_conceded": int(stats.get("goals_conceded", 0)),
                    "bonus": int(stats.get("bonus", 0)),
                    "bps": int(stats.get("bps", 0)),
                    "influence": float(stats.get("influence", 0) or 0),
                    "creativity": float(stats.get("creativity", 0) or 0),
                    "threat": float(stats.get("threat", 0) or 0),
                    "ict_index": float(stats.get("ict_index", 0) or 0),
                    "expected_goals": float(stats.get("expected_goals", 0) or 0),
                    "expected_assists": float(stats.get("expected_assists", 0) or 0),
                }
                current = existing.get((player.fpl_element_id, gw.number))
                if current:
                    for key, value in parsed.items():
                        setattr(current, key, value)
                    continue
                stat = PlayerGameweekStat(
                    season_id=season.id,
                    fpl_element_id=player.fpl_element_id,
                    player_id=player.id,
                    gameweek_number=gw.number,
                    **parsed,
                )
                db.add(stat)
                existing[(player.fpl_element_id, gw.number)] = stat
                inserted += 1
            db.commit()
    finally:
        client.close()
    return inserted
