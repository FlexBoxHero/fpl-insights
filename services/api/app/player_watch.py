"""Live FPL availability, captaincy, and price-change insights."""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from fpl_shared.fpl_client import FplClient
from fpl_shared.models import Player, Team

from app.insights_service import _current_season, _full_name, _team_display

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 10 * 60
STATUS_LABELS = {"a": "Available", "d": "Doubtful", "i": "Injured", "s": "Suspended", "u": "Unavailable", "n": "Unavailable"}
RETURN_RE = re.compile(
    r"(?:expected back|suspended until)\s+(\d{1,2}\s+[A-Za-z]{3,9})",
    re.IGNORECASE,
)
UNKNOWN_RETURN_RE = re.compile(r"unknown return date", re.IGNORECASE)

_cache_lock = threading.Lock()
_bootstrap_cache: dict[str, Any] | None = None
_bootstrap_cached_at = 0.0


def _as_float(value: object, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def parse_return_date(news: str | None) -> str | None:
    text = (news or "").strip()
    if not text:
        return None
    if UNKNOWN_RETURN_RE.search(text):
        return "Unknown"
    match = RETURN_RE.search(text)
    return match.group(1) if match else None


def price_outlook(likelihood: int | None, percent: float) -> tuple[str, str]:
    """Return (label, direction) using FPL likelihood, with percent as fallback."""
    score = likelihood
    if score is None:
        if percent >= 100:
            score = 5
        elif percent >= 80:
            score = 3
        elif percent <= -100:
            score = -5
        elif percent <= -80:
            score = -3
        else:
            score = 0
    if score >= 5:
        return "Very likely to rise", "rise"
    if score >= 3:
        return "Likely to rise", "rise"
    if score >= 1:
        return "Could rise", "rise"
    if score <= -5:
        return "Very likely to drop", "drop"
    if score <= -3:
        return "Likely to drop", "drop"
    if score <= -1:
        return "Could drop", "drop"
    return "Unlikely to change", "neutral"


def _projected(el: dict[str, Any]) -> tuple[float | None, int | None]:
    projections = el.get("price_change_projections") or []
    if not projections or not isinstance(projections, list):
        return None, None
    tonight = projections[0] if isinstance(projections[0], dict) else {}
    return _as_float(tonight.get("projected_percent")), _as_int(tonight.get("likelihood"))


def _load_bootstrap(force: bool = False) -> dict[str, Any] | None:
    global _bootstrap_cache, _bootstrap_cached_at
    now = time.time()
    with _cache_lock:
        if (
            not force
            and _bootstrap_cache is not None
            and now - _bootstrap_cached_at < CACHE_TTL_SECONDS
        ):
            return _bootstrap_cache
    client = FplClient()
    try:
        data = client.bootstrap_static()
    except Exception:
        logger.warning("Could not refresh FPL bootstrap-static", exc_info=True)
        with _cache_lock:
            return _bootstrap_cache
    finally:
        client.close()
    with _cache_lock:
        _bootstrap_cache = data
        _bootstrap_cached_at = time.time()
        return _bootstrap_cache


def _player_maps(db: Session) -> tuple[dict[int, Player], dict[int, Team], dict[int, Team]]:
    season = _current_season(db)
    if not season:
        return {}, {}, {}
    players = {
        p.fpl_element_id: p
        for p in db.query(Player).filter(Player.season_id == season.id).all()
        if p.fpl_element_id
    }
    teams_by_id = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
    teams_by_fpl = {t.fpl_team_id: t for t in teams_by_id.values()}
    return players, teams_by_id, teams_by_fpl


def _brief(
    el: dict[str, Any],
    players: dict[int, Player],
    teams_by_id: dict[int, Team],
    teams_by_fpl: dict[int, Team],
    bootstrap_teams: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    fpl_id = int(el["id"])
    db_player = players.get(fpl_id)
    team_fpl_id = int(el.get("team") or 0)
    team = None
    if db_player and db_player.team_id:
        team = teams_by_id.get(db_player.team_id)
    if team is None:
        team = teams_by_fpl.get(team_fpl_id)
    boot_team = bootstrap_teams.get(team_fpl_id) or {}
    display = _team_display(team)
    if not display.get("team"):
        display = {
            "team": boot_team.get("short_name") or "",
            "team_name": boot_team.get("name") or "",
            "team_code": boot_team.get("code"),
        }
    first = el.get("first_name") or (db_player.first_name if db_player else None)
    second = el.get("second_name") or (db_player.second_name if db_player else None)
    full_name = f"{first} {second}".strip() if first and second else el.get("web_name") or ""
    if db_player:
        full_name = _full_name(db_player)
    return {
        "player_id": db_player.id if db_player else 0,
        "fpl_element_id": fpl_id,
        "web_name": el.get("web_name") or (db_player.web_name if db_player else ""),
        "full_name": full_name,
        **display,
        "position": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(
            int(el.get("element_type") or 0),
            db_player.position if db_player else "MID",
        ),
        "price": (db_player.now_cost if db_player else int(el.get("now_cost") or 0)) / 10.0,
    }


def _captain_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    current = next((ev for ev in events if ev.get("is_current")), None)
    if current and current.get("most_captained"):
        return current
    finished = [ev for ev in events if ev.get("finished") and ev.get("most_captained")]
    if finished:
        return finished[-1]
    nxt = next((ev for ev in events if ev.get("is_next") and ev.get("most_captained")), None)
    return nxt or current


def _from_bootstrap(db: Session, bootstrap: dict[str, Any]) -> dict[str, Any]:
    elements = list(bootstrap.get("elements") or [])
    events = list(bootstrap.get("events") or [])
    teams_boot = {int(t["id"]): t for t in bootstrap.get("teams") or []}
    players, teams_by_id, teams_by_fpl = _player_maps(db)
    by_id = {int(el["id"]): el for el in elements}

    injured: list[dict[str, Any]] = []
    for el in elements:
        status = str(el.get("status") or "a")
        if status not in {"i", "d"}:
            continue
        news = (el.get("news") or "").strip()
        row = _brief(el, players, teams_by_id, teams_by_fpl, teams_boot)
        row.update(
            {
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "news": news or None,
                "return_date": parse_return_date(news),
                "chance_of_playing": _as_int(el.get("chance_of_playing_next_round"))
                if el.get("chance_of_playing_next_round") is not None
                else _as_int(el.get("chance_of_playing_this_round")),
            }
        )
        injured.append(row)
    injured.sort(
        key=lambda r: (
            0 if r["status"] == "i" else 1,
            r["chance_of_playing"] if r["chance_of_playing"] is not None else 101,
            r["web_name"],
        )
    )

    booked: list[dict[str, Any]] = []
    for el in elements:
        status = str(el.get("status") or "a")
        yellows = int(el.get("yellow_cards") or 0)
        reds = int(el.get("red_cards") or 0)
        if status == "u":
            continue
        if not (status == "s" or reds > 0 or yellows >= 2):
            continue
        news = (el.get("news") or "").strip()
        row = _brief(el, players, teams_by_id, teams_by_fpl, teams_boot)
        if status == "s":
            kind = "Suspended"
        elif reds > 0:
            kind = "Sent off"
        else:
            kind = "Booked"
        row.update(
            {
                "status": status,
                "status_label": kind,
                "news": news or None,
                "return_date": parse_return_date(news),
                "yellow_cards": yellows,
                "red_cards": reds,
            }
        )
        booked.append(row)
    booked.sort(
        key=lambda r: (
            0 if r["status_label"] == "Suspended" else 1 if r["red_cards"] else 2,
            -r["red_cards"],
            -r["yellow_cards"],
            r["web_name"],
        )
    )

    captained: list[dict[str, Any]] = []
    event = _captain_event(events)
    gameweek_number = int(event["id"]) if event else None
    used: set[int] = set()
    if event:
        for element_id, badge in (
            (event.get("most_captained"), "Most captained"),
            (event.get("most_vice_captained"), "Most vice-captained"),
        ):
            if not element_id or int(element_id) in used:
                continue
            el = by_id.get(int(element_id))
            if not el:
                continue
            row = _brief(el, players, teams_by_id, teams_by_fpl, teams_boot)
            row.update(
                {
                    "badge": badge,
                    "ownership_pct": _as_float(el.get("selected_by_percent"), 0.0) or 0.0,
                }
            )
            captained.append(row)
            used.add(int(element_id))
    owned = sorted(
        (el for el in elements if int(el["id"]) not in used and str(el.get("status") or "a") != "u"),
        key=lambda el: -(_as_float(el.get("selected_by_percent"), 0.0) or 0.0),
    )
    for el in owned:
        if len(captained) >= 5:
            break
        row = _brief(el, players, teams_by_id, teams_by_fpl, teams_boot)
        row.update(
            {
                "badge": "High ownership",
                "ownership_pct": _as_float(el.get("selected_by_percent"), 0.0) or 0.0,
            }
        )
        captained.append(row)
        used.add(int(el["id"]))

    price_rows: list[dict[str, Any]] = []
    calibrating = False
    for el in elements:
        if el.get("removed") or not el.get("can_select", True) or str(el.get("status") or "a") == "u":
            continue
        if el.get("price_change_calibrating"):
            calibrating = True
        percent = _as_float(el.get("price_change_percent"), 0.0) or 0.0
        projected, likelihood = _projected(el)
        label, direction = price_outlook(likelihood, percent)
        row = _brief(el, players, teams_by_id, teams_by_fpl, teams_boot)
        row.update(
            {
                "progress_percent": round(percent, 1),
                "predicted_percent": round(projected, 1) if projected is not None else None,
                "likelihood": likelihood,
                "outlook": label,
                "direction": direction,
                "calibrating": bool(el.get("price_change_calibrating")),
            }
        )
        price_rows.append(row)
    rises = sorted(
        (r for r in price_rows if r["progress_percent"] > 0 or r["direction"] == "rise"),
        key=lambda r: -r["progress_percent"],
    )[:10]
    falls = sorted(
        (r for r in price_rows if r["progress_percent"] < 0 or r["direction"] == "drop"),
        key=lambda r: r["progress_percent"],
    )[:10]

    return {
        "source": "live",
        "gameweek_number": gameweek_number,
        "injured": injured,
        "booked": booked,
        "most_captained": captained[:5],
        "price_rises": rises,
        "price_falls": falls,
        "price_calibrating": calibrating,
    }


def _from_db(db: Session) -> dict[str, Any]:
    season = _current_season(db)
    if not season:
        return {
            "source": "database",
            "gameweek_number": None,
            "injured": [],
            "booked": [],
            "most_captained": [],
            "price_rises": [],
            "price_falls": [],
            "price_calibrating": False,
        }
    players = db.query(Player).filter(Player.season_id == season.id).all()
    teams = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}

    def brief_db(pl: Player) -> dict[str, Any]:
        team = teams.get(pl.team_id) if pl.team_id else None
        return {
            "player_id": pl.id,
            "fpl_element_id": pl.fpl_element_id,
            "web_name": pl.web_name,
            "full_name": _full_name(pl),
            **_team_display(team),
            "position": pl.position,
            "price": pl.now_cost / 10.0,
        }

    injured = []
    for pl in players:
        if pl.status not in {"i", "d"}:
            continue
        row = brief_db(pl)
        row.update(
            {
                "status": pl.status,
                "status_label": STATUS_LABELS.get(pl.status, pl.status),
                "news": pl.news,
                "return_date": parse_return_date(pl.news),
                "chance_of_playing": pl.chance_of_playing_next_round
                if pl.chance_of_playing_next_round is not None
                else pl.chance_of_playing_this_round,
            }
        )
        injured.append(row)
    injured.sort(
        key=lambda r: (
            0 if r["status"] == "i" else 1,
            r["chance_of_playing"] if r["chance_of_playing"] is not None else 101,
            r["web_name"],
        )
    )

    booked = []
    for pl in players:
        if pl.status == "u":
            continue
        if not (pl.status == "s" or pl.red_cards > 0 or pl.yellow_cards >= 2):
            continue
        row = brief_db(pl)
        if pl.status == "s":
            kind = "Suspended"
        elif pl.red_cards > 0:
            kind = "Sent off"
        else:
            kind = "Booked"
        row.update(
            {
                "status": pl.status,
                "status_label": kind,
                "news": pl.news,
                "return_date": parse_return_date(pl.news),
                "yellow_cards": pl.yellow_cards,
                "red_cards": pl.red_cards,
            }
        )
        booked.append(row)
    booked.sort(
        key=lambda r: (
            0 if r["status_label"] == "Suspended" else 1 if r["red_cards"] else 2,
            -r["red_cards"],
            -r["yellow_cards"],
            r["web_name"],
        )
    )

    owned = sorted(
        (pl for pl in players if pl.status != "u"),
        key=lambda pl: -pl.selected_by_percent,
    )[:5]
    captained = []
    for pl in owned:
        row = brief_db(pl)
        row.update({"badge": "High ownership", "ownership_pct": pl.selected_by_percent})
        captained.append(row)

    price_rows = []
    calibrating = False
    for pl in players:
        if pl.status == "u":
            continue
        percent = pl.price_change_percent or 0.0
        label, direction = price_outlook(pl.price_change_likelihood, percent)
        if pl.price_change_calibrating:
            calibrating = True
        row = brief_db(pl)
        row.update(
            {
                "progress_percent": round(percent, 1),
                "predicted_percent": round(pl.price_change_projected_percent, 1)
                if pl.price_change_projected_percent is not None
                else None,
                "likelihood": pl.price_change_likelihood,
                "outlook": label,
                "direction": direction,
                "calibrating": pl.price_change_calibrating,
            }
        )
        price_rows.append(row)
    rises = sorted(
        (r for r in price_rows if r["progress_percent"] > 0 or r["direction"] == "rise"),
        key=lambda r: -r["progress_percent"],
    )[:10]
    falls = sorted(
        (r for r in price_rows if r["progress_percent"] < 0 or r["direction"] == "drop"),
        key=lambda r: r["progress_percent"],
    )[:10]

    return {
        "source": "database",
        "gameweek_number": None,
        "injured": injured,
        "booked": booked,
        "most_captained": captained,
        "price_rises": rises,
        "price_falls": falls,
        "price_calibrating": calibrating,
    }


def player_watch(db: Session) -> dict[str, Any]:
    bootstrap = _load_bootstrap()
    if bootstrap:
        try:
            return _from_bootstrap(db, bootstrap)
        except Exception:
            logger.exception("Failed to build player watch from live FPL data")
    return _from_db(db)
