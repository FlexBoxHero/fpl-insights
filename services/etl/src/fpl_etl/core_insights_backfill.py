"""Load a completed season from olbauday/FPL-Core-Insights GitHub CSVs."""

from __future__ import annotations

import hashlib
from urllib.parse import quote

import httpx
import pandas as pd
from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from fpl_etl.vaastav_backfill import ELEMENT_TYPE_MAP, _read_csv_bytes, _safe_float, _safe_int, ensure_season
from fpl_shared.config import settings
from fpl_shared.models import Fixture, Gameweek, Player, PlayerGameweekStat, Team

CORE_SEASONS = ["2025-26"]
CORE_SEASON_FOLDERS = {"2025-26": "2025-2026"}
CORE_POSITION_MAP = {
    "goalkeeper": "GK",
    "gk": "GK",
    "gkp": "GK",
    "defender": "DEF",
    "def": "DEF",
    "midfielder": "MID",
    "mid": "MID",
    "forward": "FWD",
    "fwd": "FWD",
}


def _core_url(season_folder: str, *parts: str) -> str:
    encoded = "/".join(quote(part, safe="") for part in parts)
    return f"{settings.fpl_core_base_url}/{season_folder}/{encoded}"


def _fetch_core_csv(season_folder: str, *parts: str) -> pd.DataFrame | None:
    url = _core_url(season_folder, *parts)
    response = httpx.get(
        url, timeout=120.0, follow_redirects=True, verify=settings.http_verify_ssl
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return _read_csv_bytes(response.content)


def _map_position(raw: object) -> str:
    if isinstance(raw, (int, float)) and not pd.isna(raw):
        return ELEMENT_TYPE_MAP.get(int(raw), "MID")
    key = str(raw or "MID").strip().lower()
    return CORE_POSITION_MAP.get(key, str(raw or "MID")[:8].upper())


def _cost_tenths(value: object) -> int:
    cost = _safe_float(value)
    if cost <= 0:
        return 0
    if cost < 30:
        return int(round(cost * 10))
    return int(round(cost))


def _stable_fixture_id(row: pd.Series) -> int:
    fotmob = _safe_int(row.get("fotmob_id"))
    if fotmob:
        return fotmob % (2**31 - 1)
    match_id = str(row.get("match_id") or row.get("id") or "")
    digest = hashlib.md5(match_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2**31 - 1)


def _parse_kickoff(value: object):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return date_parser.isoparse(str(value))
    except (ValueError, TypeError):
        return None


def load_core_insights_season(db: Session, season_code: str) -> dict[str, int]:
    folder = CORE_SEASON_FOLDERS.get(season_code)
    if not folder:
        raise ValueError(f"No Core Insights folder mapped for {season_code}")

    season = ensure_season(db, season_code, is_current=False)

    teams_df = _fetch_core_csv(folder, "teams.csv")
    if teams_df is None:
        raise FileNotFoundError(f"Core Insights teams.csv missing for {season_code}")

    team_by_fpl: dict[int, Team] = {}
    team_by_code: dict[int, Team] = {}
    for _, row in teams_df.iterrows():
        fpl_id = _safe_int(row.get("id"))
        if not fpl_id:
            continue
        team = (
            db.query(Team)
            .filter(Team.season_id == season.id, Team.fpl_team_id == fpl_id)
            .first()
        )
        if not team:
            team = Team(
                season_id=season.id,
                fpl_team_id=fpl_id,
                name=str(row.get("name", "")),
                short_name=str(row.get("short_name", row.get("name", "")))[:8],
                code=_safe_int(row.get("code"), 0) or None,
            )
            db.add(team)
            db.flush()
        team_by_fpl[fpl_id] = team
        code = _safe_int(row.get("code"))
        if code:
            team_by_code[code] = team
    db.commit()

    players_df = _fetch_core_csv(folder, "players.csv")
    if players_df is None:
        raise FileNotFoundError(f"Core Insights players.csv missing for {season_code}")

    element_to_player: dict[int, Player] = {}
    for _, row in players_df.iterrows():
        element_id = _safe_int(row.get("player_id") or row.get("id"))
        if not element_id:
            continue
        team_code = _safe_int(row.get("team_code") or row.get("team"))
        team = team_by_code.get(team_code) or team_by_fpl.get(team_code)
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
                web_name=str(row.get("web_name", "Unknown"))[:128],
                first_name=str(row.get("first_name") or "")[:64] or None,
                second_name=str(row.get("second_name") or "")[:64] or None,
                position=_map_position(row.get("position")),
                now_cost=0,
                selected_by_percent=0.0,
            )
            db.add(player)
            db.flush()
        element_to_player[element_id] = player
    db.commit()

    gw_map: dict[int, Gameweek] = {}
    fixtures_count = 0
    stats_count = 0

    for gw_num in range(1, 39):
        gw_label = f"GW{gw_num}"
        stats_df = _fetch_core_csv(folder, "By Gameweek", gw_label, "player_gameweek_stats.csv")
        fixtures_df = _fetch_core_csv(folder, "By Gameweek", gw_label, "fixtures.csv")
        if fixtures_df is None:
            fixtures_df = _fetch_core_csv(folder, "By Gameweek", gw_label, "matches.csv")

        if fixtures_df is None and stats_df is None:
            continue
        print(f"Loading Core Insights {season_code} {gw_label}...")

        gw = (
            db.query(Gameweek)
            .filter(Gameweek.season_id == season.id, Gameweek.number == gw_num)
            .first()
        )
        if not gw:
            gw = Gameweek(
                season_id=season.id,
                number=gw_num,
                name=f"Gameweek {gw_num}",
                finished=True,
            )
            db.add(gw)
            db.flush()
        gw_map[gw_num] = gw

        if fixtures_df is not None:
            if "tournament" in fixtures_df.columns:
                tourney = fixtures_df["tournament"].fillna("prem").astype(str).str.lower()
                fixtures_df = fixtures_df[tourney.isin(["prem", "pl", ""])]
            for _, row in fixtures_df.iterrows():
                home_key = _safe_int(row.get("home_team") or row.get("team_h"))
                away_key = _safe_int(row.get("away_team") or row.get("team_a"))
                home_team = team_by_code.get(home_key) or team_by_fpl.get(home_key)
                away_team = team_by_code.get(away_key) or team_by_fpl.get(away_key)
                if not home_team or not away_team:
                    continue
                fpl_fixture_id = _stable_fixture_id(row)
                if not fpl_fixture_id:
                    continue
                fixture = (
                    db.query(Fixture)
                    .filter(
                        Fixture.season_id == season.id,
                        Fixture.fpl_fixture_id == fpl_fixture_id,
                    )
                    .first()
                )
                if fixture:
                    continue
                finished = row.get("finished", True)
                if isinstance(finished, str):
                    finished = finished.strip().lower() in {"true", "1", "yes"}
                else:
                    finished = bool(finished)
                home_score = row.get("home_score", row.get("team_h_score"))
                away_score = row.get("away_score", row.get("team_a_score"))
                db.add(
                    Fixture(
                        season_id=season.id,
                        fpl_fixture_id=fpl_fixture_id,
                        gameweek_id=gw.id,
                        gameweek_number=gw_num,
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        kickoff_time=_parse_kickoff(row.get("kickoff_time")),
                        finished=finished,
                        home_score=_safe_int(home_score) if pd.notna(home_score) else None,
                        away_score=_safe_int(away_score) if pd.notna(away_score) else None,
                    )
                )
                fixtures_count += 1
            db.commit()

        if stats_df is None:
            continue
        id_col = "id" if "id" in stats_df.columns else "element"
        gw_col = "gw" if "gw" in stats_df.columns else "GW"
        if gw_col in stats_df.columns:
            stats_df = stats_df.dropna(subset=[id_col, gw_col])
            stats_df = stats_df.drop_duplicates(subset=[id_col, gw_col], keep="last")
        else:
            stats_df = stats_df.dropna(subset=[id_col])
            stats_df = stats_df.drop_duplicates(subset=[id_col], keep="last")

        for _, row in stats_df.iterrows():
            element_id = _safe_int(row.get(id_col))
            row_gw = _safe_int(row.get(gw_col), gw_num) if gw_col in stats_df.columns else gw_num
            if not element_id or row_gw < 1:
                continue
            existing = (
                db.query(PlayerGameweekStat)
                .filter(
                    PlayerGameweekStat.season_id == season.id,
                    PlayerGameweekStat.fpl_element_id == element_id,
                    PlayerGameweekStat.gameweek_number == row_gw,
                )
                .first()
            )
            if existing:
                continue
            player = element_to_player.get(element_id)
            if player:
                player.now_cost = _cost_tenths(row.get("now_cost") or row.get("value")) or player.now_cost
                if pd.notna(row.get("selected_by_percent")):
                    player.selected_by_percent = _safe_float(row.get("selected_by_percent"))
            db.add(
                PlayerGameweekStat(
                    season_id=season.id,
                    fpl_element_id=element_id,
                    player_id=player.id if player else None,
                    gameweek_number=row_gw,
                    total_points=_safe_int(row.get("total_points")),
                    minutes=_safe_int(row.get("minutes")),
                    goals_scored=_safe_int(row.get("goals_scored")),
                    assists=_safe_int(row.get("assists")),
                    clean_sheets=_safe_int(row.get("clean_sheets")),
                    goals_conceded=_safe_int(row.get("goals_conceded")),
                    bonus=_safe_int(row.get("bonus")),
                    bps=_safe_int(row.get("bps")),
                    influence=_safe_float(row.get("influence")),
                    creativity=_safe_float(row.get("creativity")),
                    threat=_safe_float(row.get("threat")),
                    ict_index=_safe_float(row.get("ict_index")),
                    expected_goals=_safe_float(row.get("expected_goals") or row.get("xG")),
                    expected_assists=_safe_float(row.get("expected_assists") or row.get("xA")),
                    xP=_safe_float(row.get("xP")) if pd.notna(row.get("xP")) else None,
                )
            )
            stats_count += 1
            if stats_count % 5000 == 0:
                db.commit()
        db.commit()

    return {
        "teams": len(team_by_fpl),
        "players": len(element_to_player),
        "fixtures": fixtures_count,
        "player_gw_rows": stats_count,
    }


def backfill_all_core_insights(
    db: Session, seasons: list[str] | None = None
) -> dict[str, dict[str, int]]:
    seasons = seasons or CORE_SEASONS
    results: dict[str, dict[str, int]] = {}
    for code in seasons:
        print(f"Backfilling Core Insights {code}...")
        results[code] = load_core_insights_season(db, code)
    return results
