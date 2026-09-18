"""Ingest EPL match results from Datahub / football-data.co.uk mirror."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import httpx
import pandas as pd
from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from fpl_shared.config import settings
from fpl_shared.models import Fixture, MatchStat, Season, Team, TeamNameAlias
from fpl_shared.team_aliases import DEFAULT_ALIASES

def _football_data_code(season_code: str) -> str:
    """Map 2024-25 -> 2425 for football-data.co.uk paths."""
    start, end = season_code.split("-")
    return f"{start[-2:]}{end}"

FALLBACK_FOOTBALL_DATA_URL = (
    "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"
)


def _alias_map(db: Session) -> dict[str, str]:
    mapping = dict(DEFAULT_ALIASES)
    for row in db.query(TeamNameAlias).all():
        mapping[row.fpl_short_name] = row.football_data_name
    return mapping


def _reverse_alias(aliases: dict[str, str]) -> dict[str, str]:
    return {v.lower(): k for k, v in aliases.items()}


def _fetch_season_csv(season_code: str) -> pd.DataFrame:
    fb_code = _football_data_code(season_code)
    url = FALLBACK_FOOTBALL_DATA_URL.format(code=fb_code)
    response = httpx.get(
        url, timeout=120.0, follow_redirects=True, verify=settings.http_verify_ssl
    )
    response.raise_for_status()
    return pd.read_csv(io.BytesIO(response.content))


def _parse_date(value: object) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return date_parser.parse(text).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _find_fixture(
    db: Session,
    season: Season,
    match_date: datetime | None,
    home_name: str,
    away_name: str,
    aliases: dict[str, str],
) -> Fixture | None:
    rev = _reverse_alias(aliases)
    home_short = rev.get(home_name.lower())
    away_short = rev.get(away_name.lower())
    if not home_short or not away_short:
        return None
    home_team = (
        db.query(Team)
        .filter(Team.season_id == season.id, Team.short_name == home_short)
        .first()
    )
    away_team = (
        db.query(Team)
        .filter(Team.season_id == season.id, Team.short_name == away_short)
        .first()
    )
    if not home_team or not away_team:
        return None
    q = db.query(Fixture).filter(
        Fixture.season_id == season.id,
        Fixture.home_team_id == home_team.id,
        Fixture.away_team_id == away_team.id,
    )
    if match_date:
        day = match_date.date()
        for fx in q.all():
            if fx.kickoff_time and fx.kickoff_time.date() == day:
                return fx
    return q.first()


DEFAULT_MATCH_SEASONS = [
    "2018-19",
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
    "2026-27",
]


def ingest_match_stats(db: Session, season_codes: list[str] | None = None) -> dict[str, int]:
    season_codes = season_codes or DEFAULT_MATCH_SEASONS
    aliases = _alias_map(db)
    inserted = 0
    linked = 0

    for code in season_codes:
        season = db.query(Season).filter(Season.code == code).first()
        if not season:
            continue
        try:
            df = _fetch_season_csv(code)
        except httpx.HTTPError:
            continue

        home_col = "HomeTeam" if "HomeTeam" in df.columns else "home_team"
        away_col = "AwayTeam" if "AwayTeam" in df.columns else "away_team"
        fthg = "FTHG" if "FTHG" in df.columns else "home_goals"
        ftag = "FTAG" if "FTAG" in df.columns else "away_goals"
        date_col = "Date" if "Date" in df.columns else "date"

        for _, row in df.iterrows():
            home_name = str(row.get(home_col, "")).strip()
            away_name = str(row.get(away_col, "")).strip()
            if not home_name or not away_name:
                continue
            match_date = _parse_date(row.get(date_col))
            home_goals = row.get(fthg)
            away_goals = row.get(ftag)
            if pd.isna(home_goals) or pd.isna(away_goals):
                continue

            existing = (
                db.query(MatchStat)
                .filter(
                    MatchStat.season_code == code,
                    MatchStat.home_team_name == home_name,
                    MatchStat.away_team_name == away_name,
                    MatchStat.match_date == match_date,
                )
                .first()
            )
            if existing:
                continue

            fixture = _find_fixture(db, season, match_date, home_name, away_name, aliases)
            if fixture:
                linked += 1
            db.add(
                MatchStat(
                    season_code=code,
                    match_date=match_date,
                    home_team_name=home_name,
                    away_team_name=away_name,
                    home_goals=int(home_goals),
                    away_goals=int(away_goals),
                    fixture_id=fixture.id if fixture else None,
                )
            )
            inserted += 1
        db.commit()

    return {"rows_inserted": inserted, "fixtures_linked": linked}
