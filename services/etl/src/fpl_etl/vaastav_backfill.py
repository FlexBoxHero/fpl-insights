"""Load historical seasons from vaastav GitHub CSV archives."""

from __future__ import annotations

import io

import httpx
import pandas as pd
from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from fpl_etl.bulk import (
    existing_player_gw_keys,
    fixture_ids,
    flush_player_gw_rows,
    gameweeks_by_number,
    players_by_element,
    teams_by_fpl_id,
)
from fpl_etl.defcon_fields import defcon_stat_fields
from fpl_etl.gw_stat_fields import extra_gw_stat_fields
from fpl_shared.config import settings
from fpl_shared.models import Fixture, Gameweek, Player, Season, Team
from fpl_shared.team_aliases import DEFAULT_ALIASES

VAASTAV_SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24"]
ELEMENT_TYPE_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
# master_team_list names that differ from football-data / DEFAULT_ALIASES values
_EXTRA_TEAM_SHORT = {
    "man utd": "MUN",
    "spurs": "TOT",
    "sheffield utd": "SHU",
}


def _team_short_lookup() -> dict[str, str]:
    mapping = {name.lower(): short for short, name in DEFAULT_ALIASES.items()}
    mapping.update(_EXTRA_TEAM_SHORT)
    return mapping


def _read_csv_bytes(content: bytes) -> pd.DataFrame:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(content), encoding="latin-1")


def _fetch_csv(season: str, filename: str) -> pd.DataFrame:
    url = f"{settings.vaastav_base_url}/{season}/{filename}"
    response = httpx.get(
        url, timeout=120.0, follow_redirects=True, verify=settings.http_verify_ssl
    )
    response.raise_for_status()
    return _read_csv_bytes(response.content)


def _try_fetch_csv(season: str, filename: str) -> pd.DataFrame | None:
    url = f"{settings.vaastav_base_url}/{season}/{filename}"
    response = httpx.get(
        url, timeout=120.0, follow_redirects=True, verify=settings.http_verify_ssl
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return _read_csv_bytes(response.content)


def _fetch_root_csv(filename: str) -> pd.DataFrame:
    url = f"{settings.vaastav_base_url}/{filename}"
    response = httpx.get(
        url, timeout=120.0, follow_redirects=True, verify=settings.http_verify_ssl
    )
    response.raise_for_status()
    return _read_csv_bytes(response.content)


def _load_teams_df(season_code: str) -> pd.DataFrame:
    teams_df = _try_fetch_csv(season_code, "teams.csv")
    if teams_df is not None:
        return teams_df
    master = _fetch_root_csv("master_team_list.csv")
    season_teams = master[master["season"].astype(str) == season_code].copy()
    if season_teams.empty:
        raise FileNotFoundError(f"No teams.csv or master_team_list rows for {season_code}")
    short_lookup = _team_short_lookup()
    season_teams["id"] = season_teams["team"]
    season_teams["name"] = season_teams["team_name"]
    season_teams["short_name"] = season_teams["name"].map(
        lambda n: short_lookup.get(str(n).lower(), str(n)[:8].upper())
    )
    season_teams["code"] = None
    return season_teams


def _load_merged_gw(season_code: str) -> pd.DataFrame:
    merged = _try_fetch_csv(season_code, "gws/merged_gw.csv")
    if merged is not None:
        return merged
    frames: list[pd.DataFrame] = []
    for gw_num in range(1, 39):
        gw_df = _try_fetch_csv(season_code, f"gws/gw{gw_num}.csv")
        if gw_df is None:
            continue
        if "GW" not in gw_df.columns and "round" not in gw_df.columns:
            gw_df["GW"] = gw_num
        frames.append(gw_df)
    if not frames:
        raise FileNotFoundError(f"No merged_gw.csv or per-GW files for {season_code}")
    return pd.concat(frames, ignore_index=True)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def ensure_season(db: Session, code: str, is_current: bool = False) -> Season:
    season = db.query(Season).filter(Season.code == code).first()
    if season:
        season.is_current = is_current
        db.commit()
        return season
    season = Season(code=code, is_current=is_current)
    db.add(season)
    db.commit()
    db.refresh(season)
    return season


def load_vaastav_season(db: Session, season_code: str) -> dict[str, int]:
    season = ensure_season(db, season_code, is_current=False)
    print(f"Loading Vaastav {season_code} (season id {season.id})...", flush=True)

    teams_df = _load_teams_df(season_code)
    team_by_fpl = teams_by_fpl_id(db, season.id)
    for _, row in teams_df.iterrows():
        fpl_id = _safe_int(row.get("id"))
        if not fpl_id or fpl_id in team_by_fpl:
            continue
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
    db.commit()

    try:
        players_df = _fetch_csv(season_code, "players_raw.csv")
    except httpx.HTTPError:
        players_df = _fetch_csv(season_code, "cleaned_players.csv")
    element_to_player = players_by_element(db, season.id)
    for _, row in players_df.iterrows():
        element_id = _safe_int(row.get("id") or row.get("element"))
        if not element_id or element_id in element_to_player:
            continue
        team_fpl = _safe_int(row.get("team"))
        team = team_by_fpl.get(team_fpl)
        pos_raw = row.get("element_type") or row.get("position")
        if isinstance(pos_raw, (int, float)) and not pd.isna(pos_raw):
            position = ELEMENT_TYPE_MAP.get(int(pos_raw), "MID")
        else:
            position = str(pos_raw or "MID")[:8]
        player = Player(
            season_id=season.id,
            fpl_element_id=element_id,
            team_id=team.id if team else None,
            web_name=str(row.get("web_name", row.get("name", "Unknown")))[:128],
            position=position,
            now_cost=_safe_int(row.get("now_cost"), 0),
            selected_by_percent=_safe_float(row.get("selected_by_percent")),
        )
        db.add(player)
        db.flush()
        element_to_player[element_id] = player
    db.commit()

    fixtures_df = _fetch_csv(season_code, "fixtures.csv")
    gw_numbers = set()
    for _, row in fixtures_df.iterrows():
        gw = row.get("event")
        if pd.notna(gw):
            gw_numbers.add(_safe_int(gw))

    gw_map = gameweeks_by_number(db, season.id)
    for gw_num in sorted(gw_numbers):
        if gw_num in gw_map:
            continue
        gw = Gameweek(
            season_id=season.id,
            number=gw_num,
            name=f"Gameweek {gw_num}",
            finished=True,
        )
        db.add(gw)
        db.flush()
        gw_map[gw_num] = gw
    db.commit()

    existing_fixtures = fixture_ids(db, season.id)
    for _, row in fixtures_df.iterrows():
        fpl_fixture_id = _safe_int(row.get("id"))
        if not fpl_fixture_id or fpl_fixture_id in existing_fixtures:
            continue
        home_fpl = _safe_int(row.get("team_h"))
        away_fpl = _safe_int(row.get("team_a"))
        home_team = team_by_fpl.get(home_fpl)
        away_team = team_by_fpl.get(away_fpl)
        if not home_team or not away_team:
            continue
        gw_num = _safe_int(row.get("event")) if pd.notna(row.get("event")) else None
        gw_obj = gw_map.get(gw_num) if gw_num else None
        kickoff = None
        if pd.notna(row.get("kickoff_time")):
            try:
                kickoff = date_parser.isoparse(str(row["kickoff_time"]))
            except (ValueError, TypeError):
                kickoff = None
        db.add(
            Fixture(
                season_id=season.id,
                fpl_fixture_id=fpl_fixture_id,
                gameweek_id=gw_obj.id if gw_obj else None,
                gameweek_number=gw_num,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                kickoff_time=kickoff,
                finished=bool(row.get("finished", False)),
                home_score=_safe_int(row.get("team_h_score")) if pd.notna(row.get("team_h_score")) else None,
                away_score=_safe_int(row.get("team_a_score")) if pd.notna(row.get("team_a_score")) else None,
                home_difficulty=_safe_int(row.get("team_h_difficulty")) if pd.notna(row.get("team_h_difficulty")) else None,
                away_difficulty=_safe_int(row.get("team_a_difficulty")) if pd.notna(row.get("team_a_difficulty")) else None,
            )
        )
        existing_fixtures.add(fpl_fixture_id)
    db.commit()

    merged = _load_merged_gw(season_code)
    gw_col = "GW" if "GW" in merged.columns else "round"
    element_col = "element" if "element" in merged.columns else "id"
    merged = merged.dropna(subset=[element_col, gw_col])
    merged = merged.drop_duplicates(subset=[element_col, gw_col], keep="last")
    seen = existing_player_gw_keys(db, season.id)
    print(f"  {len(seen)} player-gameweek rows already in DB", flush=True)
    pending: list[dict] = []
    for _, row in merged.iterrows():
        element_id = _safe_int(row.get(element_col))
        gw_num = _safe_int(row.get("GW") or row.get("round"))
        if not element_id or not gw_num:
            continue
        key = (element_id, gw_num)
        if key in seen:
            continue
        player = element_to_player.get(element_id)
        pending.append(
            {
                "season_id": season.id,
                "fpl_element_id": element_id,
                "player_id": player.id if player else None,
                "gameweek_number": gw_num,
                "total_points": _safe_int(row.get("total_points")),
                "minutes": _safe_int(row.get("minutes")),
                "goals_scored": _safe_int(row.get("goals_scored")),
                "assists": _safe_int(row.get("assists")),
                "clean_sheets": _safe_int(row.get("clean_sheets")),
                "goals_conceded": _safe_int(row.get("goals_conceded")),
                "bonus": _safe_int(row.get("bonus")),
                "bps": _safe_int(row.get("bps")),
                "influence": _safe_float(row.get("influence")),
                "creativity": _safe_float(row.get("creativity")),
                "threat": _safe_float(row.get("threat")),
                "ict_index": _safe_float(row.get("ict_index")),
                "expected_goals": _safe_float(row.get("expected_goals") or row.get("xG")),
                "expected_assists": _safe_float(row.get("expected_assists") or row.get("xA")),
                "xP": _safe_float(row.get("xP")) if pd.notna(row.get("xP")) else None,
                **defcon_stat_fields(row.to_dict()),
                **extra_gw_stat_fields(row.to_dict()),
            }
        )
        seen.add(key)
    stats_count = flush_player_gw_rows(db, pending)

    return {
        "teams": len(team_by_fpl),
        "players": len(element_to_player),
        "fixtures": len(fixtures_df),
        "player_gw_rows": stats_count,
    }


def backfill_all_vaastav(db: Session, seasons: list[str] | None = None) -> dict[str, dict[str, int]]:
    seasons = seasons or VAASTAV_SEASONS
    results: dict[str, dict[str, int]] = {}
    for code in seasons:
        print(f"Backfilling Vaastav {code}...", flush=True)
        results[code] = load_vaastav_season(db, code)
        print(f"Finished Vaastav {code}: {results[code]}", flush=True)
    return results
