"""Squad-scoped analysis: rating, weak points, captain, and transfer ideas."""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.chip_strategy import (
    SQUAD_11_OPTIONS,
    SQUAD_15,
    first_playable_gameweek,
)
from app.insights_service import (
    _current_season,
    _full_name,
    _ratings_as_of_gw,
    _team_display,
    _team_map,
)
from fpl_ml.player_model import fixture_context
from fpl_shared.config import settings
from fpl_shared.models import Fixture, Gameweek, Player, PlayerGameweekStat, PredictionPlayerGameweek, Team

MAX_PER_CLUB = 3
BUDGET_CAP = 100.0
NEARBY_POS = {
    "GK": ("GK",),
    "DEF": ("DEF",),
    "MID": ("MID", "FWD"),
    "FWD": ("FWD", "MID"),
}


@dataclass
class SquadPlayer:
    player_id: int
    fpl_element_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None
    team_code: int | None
    team_id: int | None
    position: str
    price: float
    expected_points: float
    n_fixtures: int = 1
    opponents: str = ""
    opp_fdr: float = 3.0
    is_home: bool = False
    form: float | None = None
    last_gw: float | None = None
    is_captain: bool = False
    is_vice: bool = False
    starter: bool = False

    def as_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "fpl_element_id": self.fpl_element_id,
            "web_name": self.web_name,
            "full_name": self.full_name,
            "team": self.team,
            "team_name": self.team_name,
            "team_code": self.team_code,
            "team_id": self.team_id,
            "position": self.position,
            "price": round(self.price, 1),
            "expected_points": round(self.expected_points, 2),
            "n_fixtures": self.n_fixtures,
            "opponents": self.opponents,
            "opp_fdr": round(self.opp_fdr, 2),
            "is_home": self.is_home,
            "form": self.form,
            "last_gw": self.last_gw,
            "is_captain": self.is_captain,
            "is_vice": self.is_vice,
            "starter": self.starter,
        }


def pick_best_xi(players: list[SquadPlayer]) -> tuple[list[SquadPlayer], float, dict[str, int]]:
    by_pos: dict[str, list[SquadPlayer]] = defaultdict(list)
    for player in players:
        by_pos[player.position].append(player)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: (-p.expected_points, p.player_id))

    best: list[SquadPlayer] = []
    best_score = -1.0
    best_shape: dict[str, int] = dict(SQUAD_11_OPTIONS[0])
    for shape in SQUAD_11_OPTIONS:
        xi: list[SquadPlayer] = []
        score = 0.0
        valid = True
        for pos, n in shape.items():
            pool = by_pos.get(pos, [])
            if len(pool) < n:
                valid = False
                break
            chosen = pool[:n]
            xi.extend(chosen)
            score += sum(p.expected_points for p in chosen)
        if valid and score > best_score:
            best_score = score
            best = xi
            best_shape = dict(shape)
    return best, max(best_score, 0.0), best_shape


def formation_label(shape: dict[str, int]) -> str:
    return f"{shape.get('DEF', 0)}-{shape.get('MID', 0)}-{shape.get('FWD', 0)}"


def xi_xpts(players: list[SquadPlayer]) -> float:
    xi, score, _ = pick_best_xi(players)
    _ = xi
    return score


def score_rating(
    squad_xi: float,
    template_xi: float,
    squad_captain: float,
    league_captain: float,
    avg_fdr: float,
    issue_count: int,
) -> tuple[int, str]:
    xi_ratio = squad_xi / max(template_xi, 0.5)
    cap_ratio = squad_captain / max(league_captain, 0.5)
    fdr_score = max(0.0, min(1.0, 1.0 - (avg_fdr - 2.0) / 3.0))
    raw = 100.0 * (
        0.55 * min(xi_ratio, 1.12) / 1.12
        + 0.25 * min(cap_ratio, 1.0)
        + 0.20 * fdr_score
    )
    raw *= max(0.55, 1.0 - 0.06 * issue_count)
    rating = int(max(1, min(99, round(raw))))
    if rating >= 82:
        label = "strong"
    elif rating >= 68:
        label = "solid"
    elif rating >= 52:
        label = "mixed"
    else:
        label = "needs work"
    return rating, label


def club_counts(players: list[SquadPlayer]) -> Counter[int]:
    return Counter(p.team_id for p in players if p.team_id is not None)


def can_add_club(players: list[SquadPlayer], team_id: int | None, removing: int | None = None) -> bool:
    if team_id is None:
        return True
    counts = club_counts(players)
    if removing is not None:
        counts[removing] -= 1
    return counts[team_id] < MAX_PER_CLUB


def suggest_transfers(
    squad: list[SquadPlayer],
    pool: list[SquadPlayer],
    bank: float,
    limit: int = 4,
) -> list[dict]:
    xi, _, _ = pick_best_xi(squad)
    if not xi:
        return []
    owned = {p.player_id for p in squad}
    weakest = sorted(xi, key=lambda p: (p.expected_points, p.player_id))[:3]
    baseline = xi_xpts(squad)
    out_cards: list[dict] = []
    used_out: set[int] = set()
    used_in: set[int] = set()
    for outgoing in weakest:
        if outgoing.player_id in used_out:
            continue
        budget = outgoing.price + bank
        allowed_pos = NEARBY_POS.get(outgoing.position, (outgoing.position,))
        candidates = [
            p
            for p in pool
            if p.player_id not in owned
            and p.player_id not in used_in
            and p.position in allowed_pos
            and p.price <= budget + 1e-6
            and can_add_club(squad, p.team_id, removing=outgoing.team_id)
            and p.expected_points > outgoing.expected_points + 0.15
        ]
        candidates.sort(key=lambda p: (-p.expected_points, p.price, p.player_id))
        best_card = None
        best_gain = 0.15
        for incoming in candidates[:18]:
            trial = [p for p in squad if p.player_id != outgoing.player_id] + [incoming]
            gain = xi_xpts(trial) - baseline
            if gain > best_gain:
                best_gain = gain
                remaining = round(bank + outgoing.price - incoming.price, 1)
                best_card = {
                    "out": outgoing.as_dict(),
                    "in": incoming.as_dict(),
                    "gain": round(gain, 2),
                    "hit": False,
                    "remaining_bank": remaining,
                    "reason": (
                        f"Swap {outgoing.web_name} ({outgoing.expected_points:.1f} xPts) for "
                        f"{incoming.web_name} ({incoming.expected_points:.1f} xPts, "
                        f"{incoming.opponents or 'this GW'}). XI improves by {gain:.1f}."
                    ),
                }
        if best_card:
            out_cards.append(best_card)
            used_out.add(outgoing.player_id)
            used_in.add(best_card["in"]["player_id"])
        if len(out_cards) >= limit:
            break
    return out_cards


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ø", "o").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "", text)


def match_player_name(
    raw_name: str,
    players: list[Player],
    used: set[int],
    position: str | None = None,
) -> tuple[Player | None, float]:
    needle = normalize_name(raw_name)
    if not needle:
        return None, 0.0
    want_pos = (position or "").strip().upper() or None
    best: Player | None = None
    best_score = 0.0
    for player in players:
        if player.id in used:
            continue
        score = _name_score(needle, player)
        if want_pos and (player.position or "").upper() == want_pos:
            score = min(1.0, score + 0.04)
        if score > best_score:
            best_score = score
            best = player
    if best is None or best_score < 0.78:
        return None, best_score
    return best, round(min(best_score, 1.0), 3)


def _name_score(needle: str, player: Player) -> float:
    web = normalize_name(player.web_name or "")
    full = normalize_name(_full_name(player))
    if web and needle == web:
        return 1.0
    if full and needle == full:
        return 0.99
    best = 0.0
    if web:
        best = max(best, difflib.SequenceMatcher(None, needle, web).ratio())
        if min(len(needle), len(web)) >= 4 and (needle.startswith(web) or web.startswith(needle)):
            best = max(best, 0.94)
    if full:
        best = max(best, difflib.SequenceMatcher(None, needle, full).ratio())
    return best


def analyze_squad(
    db: Session,
    picks: list[dict],
    *,
    bank: float = 0.0,
    free_transfers: int = 1,
    entry: dict | None = None,
) -> dict:
    season = _current_season(db)
    if not season:
        raise ValueError("No season loaded.")
    gameweeks = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id)
        .order_by(Gameweek.number)
        .all()
    )
    gw = first_playable_gameweek(gameweeks)
    teams = _team_map(db, season.id)
    fixtures = (
        db.query(Fixture)
        .filter(Fixture.season_id == season.id, Fixture.gameweek_number == gw)
        .all()
    )
    fx_index: dict[int, list[Fixture]] = defaultdict(list)
    for fx in fixtures:
        fx_index[fx.home_team_id].append(fx)
        fx_index[fx.away_team_id].append(fx)
    ratings = _ratings_as_of_gw(db, season, gw, teams)
    preds = _prediction_map(db, gw)
    last_gw_map = _last_gw_points(db, season.id, gw)

    resolved = _resolve_picks(db, season.id, picks, teams, fx_index, ratings, preds, last_gw_map)
    if len(resolved) < 11:
        raise ValueError("Need at least 11 matched players to analyse a squad.")

    forced_starters = [p for p in resolved if p.starter]
    if len(forced_starters) == 11:
        xi = forced_starters
        shape = Counter(p.position for p in xi)
        xi_score = sum(p.expected_points for p in xi)
        shape_dict = {pos: int(shape.get(pos, 0)) for pos in ("GK", "DEF", "MID", "FWD")}
    else:
        xi, xi_score, shape_dict = pick_best_xi(resolved)
    xi_ids = {p.player_id for p in xi}
    for player in resolved:
        player.starter = player.player_id in xi_ids

    pool = _pool_from_preds(db, season.id, teams, fx_index, ratings, preds, last_gw_map)
    template = _template_xi_from_pool(pool) if pool else _template_xi_xpts(preds)
    league_cap, league_cap_player = _league_best_captain(preds, db, season.id, teams)
    cap_from_xi = max(xi, key=lambda p: (p.expected_points, -p.player_id), default=None)
    user_cap = next((p for p in resolved if p.is_captain), None)
    user_vice = next((p for p in resolved if p.is_vice), None)
    rec_cap = cap_from_xi
    rec_vice = None
    if rec_cap:
        others = [p for p in xi if p.player_id != rec_cap.player_id]
        rec_vice = max(others, key=lambda p: p.expected_points, default=None)

    issues = _issues(resolved, xi, gw)
    fdrs = [p.opp_fdr for p in xi if p.n_fixtures]
    avg_fdr = sum(fdrs) / len(fdrs) if fdrs else 3.0
    cap_xp = rec_cap.expected_points if rec_cap else 0.0
    rating, label = score_rating(xi_score, template, cap_xp, league_cap, avg_fdr, len(issues))
    transfers = suggest_transfers(resolved, pool, bank)
    for card in transfers:
        card["hit"] = free_transfers < 1
        if card["hit"]:
            card["reason"] += " You have 0 FT, so this is a -4 hit."

    bench = [p for p in resolved if not p.starter]
    bench.sort(key=lambda p: -p.expected_points)
    cap_note = _captain_note(user_cap, rec_cap, league_cap_player, {p.player_id for p in resolved})
    rating_reason = (
        f"Your XI projects {xi_score:.1f} xPts vs a template best of {template:.1f}. "
        f"Captain week: {rec_cap.web_name if rec_cap else 'n/a'} "
        f"({cap_xp:.1f} → {cap_xp * 2:.1f} as C)."
    )
    return {
        "gameweek": gw,
        "entry": entry,
        "bank": round(float(bank), 1),
        "free_transfers": int(free_transfers),
        "squad_value": round(sum(p.price for p in resolved), 1),
        "rating": rating,
        "rating_label": label,
        "rating_reason": rating_reason,
        "xi_xpts": round(xi_score, 2),
        "xi_xpts_with_captain": round(xi_score + cap_xp, 2),
        "template_xi_xpts": round(template, 2),
        "bench_xpts": round(sum(p.expected_points for p in bench), 2),
        "formation": formation_label(shape_dict),
        "players": [p.as_dict() for p in sorted(resolved, key=lambda p: (not p.starter, p.position, -p.expected_points))],
        "captain": _cap_payload(rec_cap, user_cap, cap_note),
        "vice": _cap_payload(rec_vice, user_vice, None) if rec_vice else None,
        "global_captain": league_cap_player,
        "issues": issues,
        "transfers": transfers,
    }


def analyze_from_entry(db: Session, entry_id: int) -> dict:
    from fpl_shared.fpl_client import FplClient

    season = _current_season(db)
    if not season:
        raise ValueError("No season loaded.")
    gameweeks = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id)
        .order_by(Gameweek.number)
        .all()
    )
    gw = first_playable_gameweek(gameweeks)
    client = FplClient()
    try:
        entry = client.entry(entry_id)
        if entry is None:
            raise LookupError("FPL team not found. Check the ID, or that the team is public.")
        picks_payload = client.entry_picks(entry_id, gw)
        if picks_payload is None:
            prev = max(1, gw - 1)
            picks_payload = client.entry_picks(entry_id, prev)
        if picks_payload is None:
            raise LookupError("Could not load picks for this team (private or not yet set).")
    finally:
        client.close()

    raw_picks = picks_payload.get("picks") or []
    picks = []
    for row in raw_picks:
        picks.append(
            {
                "fpl_element_id": int(row["element"]),
                "is_captain": bool(row.get("is_captain")),
                "is_vice": bool(row.get("is_vice_captain")),
                "starter": int(row.get("position") or 99) <= 11,
            }
        )
    history = picks_payload.get("entry_history") or {}
    bank = float(history.get("bank") or entry.get("last_deadline_bank") or 0) / 10.0
    last_transfers = int(history.get("event_transfers") or 0)
    free_transfers = 2 if last_transfers == 0 else 1
    info = {
        "id": entry_id,
        "name": entry.get("name"),
        "manager": f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip(),
        "overall_rank": entry.get("summary_overall_rank"),
    }
    return analyze_squad(db, picks, bank=bank, free_transfers=free_transfers, entry=info)


def parse_screenshot(db: Session, image_b64: str, media_type: str = "image/png") -> dict:
    if not settings.vision_api_key:
        raise PermissionError("Screenshot parsing needs VISION_API_KEY in the API environment.")
    extracted = _vision_extract(image_b64, media_type)
    season = _current_season(db)
    if not season:
        raise ValueError("No season loaded.")
    players = db.query(Player).filter(Player.season_id == season.id).all()
    used: set[int] = set()
    matches = []
    for row in extracted:
        player, score = match_player_name(
            str(row.get("name") or ""),
            players,
            used,
            position=str(row.get("position") or "") or None,
        )
        item = {
            "raw_name": row.get("name"),
            "raw_position": row.get("position"),
            "on_bench": bool(row.get("on_bench")),
            "is_captain": bool(row.get("is_captain")),
            "is_vice": bool(row.get("is_vice")),
            "confidence": round(float(score), 3),
            "player": None,
        }
        if player:
            used.add(player.id)
            item["player"] = {
                "player_id": player.id,
                "fpl_element_id": player.fpl_element_id,
                "web_name": player.web_name,
                "full_name": _full_name(player),
                "position": player.position,
                "price": round(player.now_cost / 10.0, 1),
                "team_id": player.team_id,
            }
        matches.append(item)
    return {
        "vision_notes": extracted and extracted[0].get("_notes") or "",
        "matches": matches,
        "matched": sum(1 for m in matches if m["player"]),
        "needed": 15,
    }


def vision_enabled() -> bool:
    return bool(settings.vision_api_key)


def _prediction_map(db: Session, gw: int) -> dict[int, PredictionPlayerGameweek]:
    rows = (
        db.query(PredictionPlayerGameweek)
        .filter(PredictionPlayerGameweek.gameweek_number == gw)
        .all()
    )
    preferred = [r for r in rows if r.model_version == settings.model_version]
    use = preferred or rows
    return {r.player_id: r for r in use}


def _last_gw_points(db: Session, season_id: int, gw: int) -> dict[int, float]:
    rows = (
        db.query(PlayerGameweekStat)
        .filter(
            PlayerGameweekStat.season_id == season_id,
            PlayerGameweekStat.gameweek_number == gw - 1,
        )
        .all()
    )
    return {r.player_id: float(r.total_points) for r in rows if r.player_id}


def _index_team_fixtures(fixtures: list[Fixture]) -> dict[int, list[Fixture]]:
    index: dict[int, list[Fixture]] = defaultdict(list)
    for fx in fixtures:
        index[fx.home_team_id].append(fx)
        index[fx.away_team_id].append(fx)
    return index


def _opponent_labels(fixtures: list[Fixture], team_id: int, teams: dict[int, Team]) -> str:
    parts: list[str] = []
    for fx in fixtures:
        is_home = fx.home_team_id == team_id
        opp = teams.get(fx.away_team_id if is_home else fx.home_team_id)
        short = opp.short_name if opp else "?"
        parts.append(f"{short} ({'H' if is_home else 'A'})")
    return ", ".join(parts) if parts else "Blank"


def _hydrate_player(
    player: Player,
    teams: dict[int, Team],
    fx_index: dict[int, list[Fixture]],
    ratings: dict[int, dict[str, float]],
    preds: dict[int, PredictionPlayerGameweek],
    last_gw_map: dict[int, float],
    *,
    is_captain: bool = False,
    is_vice: bool = False,
    starter: bool = False,
) -> SquadPlayer:
    team = teams.get(player.team_id) if player.team_id else None
    display = _team_display(team)
    pred = preds.get(player.id)
    fxs = fx_index.get(player.team_id or -1, [])
    ctx = fixture_context(player, fxs, ratings) if fxs else None
    xp = float(pred.expected_points) if pred else float(player.ep_next or 0.0)
    return SquadPlayer(
        player_id=player.id,
        fpl_element_id=player.fpl_element_id,
        web_name=player.web_name,
        full_name=_full_name(player),
        team=display["team"],
        team_name=display["team_name"],
        team_code=display["team_code"],
        team_id=player.team_id,
        position=player.position,
        price=player.now_cost / 10.0,
        expected_points=xp,
        n_fixtures=int(ctx["n_fixtures"]) if ctx else 0,
        opponents=_opponent_labels(fxs, player.team_id or -1, teams) if player.team_id else "Blank",
        opp_fdr=float(ctx["opp_fdr"]) if ctx else 3.0,
        is_home=bool(ctx and ctx["is_home"] >= 0.5),
        form=player.form,
        last_gw=last_gw_map.get(player.id, pred.baseline_last_gw if pred else None),
        is_captain=is_captain,
        is_vice=is_vice,
        starter=starter,
    )


def _resolve_picks(
    db: Session,
    season_id: int,
    picks: list[dict],
    teams: dict[int, Team],
    fx_index: dict[int, list[Fixture]],
    ratings: dict[int, dict[str, float]],
    preds: dict[int, PredictionPlayerGameweek],
    last_gw_map: dict[int, float],
) -> list[SquadPlayer]:
    elements = [int(p["fpl_element_id"]) for p in picks if p.get("fpl_element_id")]
    ids = [int(p["player_id"]) for p in picks if p.get("player_id")]
    q = db.query(Player).filter(Player.season_id == season_id)
    found: list[Player] = []
    if elements:
        found.extend(q.filter(Player.fpl_element_id.in_(elements)).all())
    if ids:
        found.extend(db.query(Player).filter(Player.id.in_(ids)).all())
    by_el = {p.fpl_element_id: p for p in found}
    by_id = {p.id: p for p in found}
    resolved: list[SquadPlayer] = []
    seen: set[int] = set()
    for pick in picks:
        player = None
        if pick.get("fpl_element_id"):
            player = by_el.get(int(pick["fpl_element_id"]))
        if player is None and pick.get("player_id"):
            player = by_id.get(int(pick["player_id"]))
        if player is None or player.id in seen:
            continue
        seen.add(player.id)
        resolved.append(
            _hydrate_player(
                player,
                teams,
                fx_index,
                ratings,
                preds,
                last_gw_map,
                is_captain=bool(pick.get("is_captain")),
                is_vice=bool(pick.get("is_vice")),
                starter=bool(pick.get("starter")),
            )
        )
    return resolved


def _pool_from_preds(
    db: Session,
    season_id: int,
    teams: dict[int, Team],
    fx_index: dict[int, list[Fixture]],
    ratings: dict[int, dict[str, float]],
    preds: dict[int, PredictionPlayerGameweek],
    last_gw_map: dict[int, float],
) -> list[SquadPlayer]:
    ids = list(preds.keys())
    if not ids:
        return []
    players = db.query(Player).filter(Player.id.in_(ids)).all()
    return [
        _hydrate_player(p, teams, fx_index, ratings, preds, last_gw_map)
        for p in players
        if p.season_id == season_id
    ]


def _template_xi_xpts(preds: dict[int, PredictionPlayerGameweek]) -> float:
    # Fallback if we cannot join positions here — caller should prefer DB-backed pool.
    scores = sorted((float(p.expected_points) for p in preds.values()), reverse=True)
    return sum(scores[:11]) if scores else 50.0


def _league_best_captain(
    preds: dict[int, PredictionPlayerGameweek],
    db: Session,
    season_id: int,
    teams: dict[int, Team],
) -> tuple[float, dict | None]:
    if not preds:
        return 0.0, None
    best_id, best_pred = max(preds.items(), key=lambda kv: kv[1].expected_points)
    player = db.query(Player).filter(Player.id == best_id).first()
    if not player:
        return float(best_pred.expected_points), None
    team = teams.get(player.team_id) if player.team_id else None
    display = _team_display(team)
    xp = float(best_pred.expected_points)
    return xp, {
        "player_id": player.id,
        "web_name": player.web_name,
        "full_name": _full_name(player),
        "team": display["team"],
        "team_name": display["team_name"],
        "team_code": display["team_code"],
        "position": player.position,
        "expected_points": round(xp, 2),
        "captain_expected_points": round(xp * 2.0, 2),
    }


def _issues(squad: list[SquadPlayer], xi: list[SquadPlayer], gw: int) -> list[dict]:
    issues: list[dict] = []
    by_club = club_counts(squad)
    for team_id, n in by_club.items():
        if n >= 3:
            names = [p.web_name for p in squad if p.team_id == team_id]
            club = next((p.team for p in squad if p.team_id == team_id), "?")
            issues.append(
                {
                    "code": "club_limit",
                    "severity": "medium",
                    "title": f"{n} players from {club}",
                    "detail": f"{', '.join(names)} — a blank or tough run hits the whole chunk.",
                    "player_id": None,
                }
            )
    for player in xi:
        if player.n_fixtures <= 0:
            issues.append(
                {
                    "code": "blank",
                    "severity": "high",
                    "title": f"{player.web_name} blanks GW{gw}",
                    "detail": "No fixture this week — they should not start.",
                    "player_id": player.player_id,
                }
            )
        elif player.opp_fdr >= 4.15:
            issues.append(
                {
                    "code": "hard_fixture",
                    "severity": "medium",
                    "title": f"{player.web_name} faces a tough fixture",
                    "detail": f"{player.opponents} (FDR {player.opp_fdr:.1f}).",
                    "player_id": player.player_id,
                }
            )
        if player.expected_points < 2.2 and player.position != "GK":
            issues.append(
                {
                    "code": "low_xpts",
                    "severity": "high" if player.expected_points < 1.4 else "medium",
                    "title": f"{player.web_name} is a weak starter ({player.expected_points:.1f} xPts)",
                    "detail": "Among the first names to upgrade this week.",
                    "player_id": player.player_id,
                }
            )
        if player.form is not None and player.form < 1.5 and player.expected_points < 3.5:
            issues.append(
                {
                    "code": "rotation",
                    "severity": "low",
                    "title": f"{player.web_name} looks rotation-prone",
                    "detail": f"FPL form {player.form:.1f} with modest xPts.",
                    "player_id": player.player_id,
                }
            )
    # Keep the list readable
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (severity_rank.get(i["severity"], 9), i["title"]))
    return issues[:8]


def _captain_note(
    user_cap: SquadPlayer | None,
    rec_cap: SquadPlayer | None,
    global_cap: dict | None,
    squad_ids: set[int],
) -> str:
    if not rec_cap:
        return "No captain candidate in this XI."
    parts = [
        f"Best in your XI: {rec_cap.web_name} ({rec_cap.expected_points:.1f} xPts, "
        f"{rec_cap.expected_points * 2:.1f} as captain) vs {rec_cap.opponents or 'this GW'}."
    ]
    if user_cap and user_cap.player_id != rec_cap.player_id:
        parts.append(
            f"Your current captain {user_cap.web_name} projects {user_cap.expected_points:.1f}."
        )
    if global_cap and global_cap.get("player_id") != rec_cap.player_id:
        name = global_cap["web_name"]
        xp = global_cap["expected_points"]
        if global_cap.get("player_id") in squad_ids:
            parts.append(f"League-wide best is {name} ({xp:.1f}) — in your squad.")
        else:
            parts.append(f"League-wide best {name} ({xp:.1f}) is not in your squad.")
    return " ".join(parts)


def _cap_payload(
    rec: SquadPlayer | None, user: SquadPlayer | None, note: str | None
) -> dict | None:
    if not rec:
        return None
    return {
        **rec.as_dict(),
        "captain_expected_points": round(rec.expected_points * 2.0, 2),
        "is_user_pick": bool(user and user.player_id == rec.player_id),
        "note": note,
    }


def _vision_http_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict) and item.get("error"):
                message = item["error"].get("message")
                if message:
                    return str(message)
        return str(payload)
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def _vision_extract(image_b64: str, media_type: str) -> list[dict]:
    raw = image_b64.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    url = settings.vision_api_base.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.vision_model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You read Fantasy Premier League squad screenshots. "
                    "Return JSON only: {\"players\":[{\"name\":\"web_name\",\"position\":\"GK|DEF|MID|FWD\","
                    "\"on_bench\":false,\"is_captain\":false,\"is_vice\":false}], \"notes\":\"\"}. "
                    "Exactly the 15 players if visible. Use FPL web names (Haaland, Saka, B.Fernandes)."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the 15 FPL players from this squad screenshot."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{raw}"},
                    },
                ],
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.vision_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload, headers=headers)
        if not response.is_success:
            raise RuntimeError(_vision_http_error(response))
        body = response.json()
    text = body["choices"][0]["message"]["content"]
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    data = json.loads(text)
    players = data.get("players") or []
    notes = data.get("notes") or ""
    if players:
        players[0]["_notes"] = notes
    return players


def _template_xi_from_pool(pool: list[SquadPlayer]) -> float:
    _, score, _ = pick_best_xi(pool)
    return score
