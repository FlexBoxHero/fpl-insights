"""Chip strategy: when to play Wildcard, Bench Boost, Triple Captain, and Free Hit."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.insights_service import (
    _current_season,
    _fixture_outcomes,
    _full_name,
    _ratings_as_of_gw,
    _team_display,
    _team_map,
)
from fpl_ml.difficulty_scale import blend_with_fpl_fdr, raw_difficulty_from_lambdas
from fpl_ml.player_model import fixture_context
from fpl_shared.config import settings
from fpl_shared.models import Fixture, Gameweek, Player, PredictionPlayerGameweek, Team

CHIP_IDS = ("wildcard", "bench_boost", "triple_captain", "free_hit")
CHIP_LABELS = {
    "wildcard": "Wildcard",
    "bench_boost": "Bench Boost",
    "triple_captain": "Triple Captain",
    "free_hit": "Free Hit",
}
CHIP_ALIASES = {
    "wc": "wildcard",
    "bb": "bench_boost",
    "tc": "triple_captain",
    "fh": "free_hit",
}
HALVES = {
    "first": (1, 19),
    "second": (20, 38),
}
SQUAD_15 = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
SQUAD_11_OPTIONS = (
    {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
    {"GK": 1, "DEF": 3, "MID": 5, "FWD": 2},
    {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
    {"GK": 1, "DEF": 5, "MID": 4, "FWD": 1},
)
WINDOW_LIMIT = 4
NOTES = (
    "Suggestions use remaining fixtures, predicted points, and typical FPL chip timing. "
    "They are league-wide (not based on your squad). Only one chip can be played in a "
    "gameweek. Each chip can be used once in GW1–19 and once in GW20–38."
)


@dataclass
class CaptainPick:
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None
    team_code: int | None
    position: str
    expected_points: float
    n_fixtures: int
    opponents: str
    is_home: bool = False
    expected_goals: float = 0.0

    @property
    def triple_expected_points(self) -> float:
        return round(self.expected_points * 3.0, 2)


@dataclass
class GwProfile:
    gameweek: int
    n_matches: int
    blank_teams: int
    double_teams: int
    avg_fdr: float
    easy_fixtures: int
    template_15_xpts: float
    template_11_xpts: float
    fixture_swing: float
    easy_run_teams: int
    upcoming_dgw: bool
    top_captain: CaptainPick | None
    half_end: int
    playable_start: int


@dataclass(frozen=True)
class ChipWindow:
    chip: str
    gameweek: int
    score: float
    confidence: str
    headline: str
    reason: str
    flags: tuple[str, ...] = ()
    player: CaptainPick | None = None

    def as_dict(self) -> dict:
        out = {
            "chip": self.chip,
            "chip_label": CHIP_LABELS[self.chip],
            "gameweek": self.gameweek,
            "score": round(self.score, 3),
            "confidence": self.confidence,
            "headline": self.headline,
            "reason": self.reason,
            "flags": list(self.flags),
            "player": None,
        }
        if self.player:
            out["player"] = {
                "player_id": self.player.player_id,
                "web_name": self.player.web_name,
                "full_name": self.player.full_name,
                "team": self.player.team,
                "team_name": self.player.team_name,
                "team_code": self.player.team_code,
                "position": self.player.position,
                "expected_points": round(self.player.expected_points, 2),
                "triple_expected_points": self.player.triple_expected_points,
                "n_fixtures": self.player.n_fixtures,
                "opponents": self.player.opponents,
                "is_home": self.player.is_home,
                "expected_goals": round(self.player.expected_goals, 2),
            }
        return out


def parse_chips(raw: str | None, *, default_all: bool = True) -> list[str]:
    if raw is None:
        return list(CHIP_IDS) if default_all else []
    if not raw.strip():
        return []
    out: list[str] = []
    for part in raw.split(","):
        key = part.strip().lower().replace(" ", "_").replace("-", "_")
        key = CHIP_ALIASES.get(key, key)
        if key in CHIP_IDS and key not in out:
            out.append(key)
    return out


def score_triple_captain(profile: GwProfile) -> float:
    cap = profile.top_captain
    if not cap or cap.n_fixtures <= 0:
        return 0.0
    dgw_bonus = 5.0 if cap.n_fixtures >= 2 else 0.0
    home_bonus = 1.2 if cap.is_home else 0.0
    return (
        cap.expected_points * (1.0 + 0.6 * max(0, cap.n_fixtures - 1))
        + dgw_bonus
        + home_bonus
        + 2.2 * cap.expected_goals
    )


def score_bench_boost(profile: GwProfile) -> float:
    return (
        profile.template_15_xpts
        + 4.5 * profile.double_teams
        - 3.5 * profile.blank_teams
        + (8.0 if profile.double_teams >= 4 else 0.0)
    )


def score_free_hit(profile: GwProfile) -> float:
    return (
        6.5 * profile.blank_teams
        + 0.4 * profile.template_11_xpts
        + 1.1 * profile.easy_fixtures
        - 2.2 * profile.double_teams
        + (10.0 if profile.blank_teams >= 4 else 0.0)
    )


def score_wildcard(profile: GwProfile) -> float:
    leftover = profile.half_end - profile.gameweek
    late_pen = 0.45 if leftover <= 1 else (0.7 if leftover <= 2 else 1.0)
    bgw_pen = 0.6 if profile.blank_teams >= 4 else 1.0
    dgw_prep = 4.0 if profile.upcoming_dgw else 0.0
    early_span = max(profile.half_end - profile.playable_start, 1)
    early_nudge = 1.2 * (1.0 - (profile.gameweek - profile.playable_start) / early_span)
    raw = 11.0 * profile.fixture_swing + 1.5 * profile.easy_run_teams + dgw_prep + early_nudge
    return max(0.0, raw) * late_pen * bgw_pen


def assign_plan(
    windows_by_chip: dict[str, list[ChipWindow]], available: list[str]
) -> list[ChipWindow]:
    ranked: list[ChipWindow] = []
    for chip in available:
        ranked.extend(windows_by_chip.get(chip, [])[:10])
    ranked.sort(key=lambda w: (-w.score, w.gameweek))
    used_gws: set[int] = set()
    used_chips: set[str] = set()
    chosen: list[ChipWindow] = []
    for window in ranked:
        if window.chip in used_chips or window.gameweek in used_gws:
            continue
        chosen.append(window)
        used_chips.add(window.chip)
        used_gws.add(window.gameweek)
        if len(chosen) == len(available):
            break
    chosen = _prefer_wildcard_before_attacking(chosen, windows_by_chip)
    chosen.sort(key=lambda w: w.gameweek)
    return chosen


def _prefer_wildcard_before_attacking(
    chosen: list[ChipWindow],
    windows_by_chip: dict[str, list[ChipWindow]],
) -> list[ChipWindow]:
    by_chip = {w.chip: w for w in chosen}
    wildcard = by_chip.get("wildcard")
    if not wildcard:
        return chosen
    attack_gws = [
        by_chip[chip].gameweek for chip in ("bench_boost", "triple_captain") if chip in by_chip
    ]
    if not attack_gws or wildcard.gameweek < min(attack_gws):
        return chosen
    earliest_attack = min(attack_gws)
    taken = {w.gameweek for w in chosen if w.chip != "wildcard"}
    for alt in windows_by_chip.get("wildcard", []):
        if alt.gameweek < earliest_attack and alt.gameweek not in taken:
            by_chip["wildcard"] = alt
            break
    return list(by_chip.values())


def first_playable_gameweek(gameweeks: list[Gameweek], now: datetime | None = None) -> int:
    nxt = next((g for g in gameweeks if g.is_next), None)
    if nxt:
        return nxt.number
    now = now or datetime.now(timezone.utc)
    current = next((g for g in gameweeks if g.is_current), None)
    if current:
        deadline = current.deadline_time
        if deadline is not None:
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline > now and not current.finished:
                return current.number
        return current.number + 1
    open_gw = next((g for g in gameweeks if not g.finished), None)
    return open_gw.number if open_gw else 39


def build_chip_strategy(
    db: Session,
    first_chips: list[str] | None = None,
    second_chips: list[str] | None = None,
) -> dict:
    first_chips = [c for c in (first_chips if first_chips is not None else list(CHIP_IDS)) if c in CHIP_IDS]
    second_chips = [c for c in (second_chips if second_chips is not None else list(CHIP_IDS)) if c in CHIP_IDS]
    season = _current_season(db)
    empty = _empty_payload(first_chips, second_chips)
    if not season:
        return empty

    gameweeks = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id)
        .order_by(Gameweek.number)
        .all()
    )
    playable = first_playable_gameweek(gameweeks)
    teams = _team_map(db, season.id)
    fixtures = (
        db.query(Fixture)
        .filter(Fixture.season_id == season.id, Fixture.gameweek_number.isnot(None))
        .all()
    )
    players = db.query(Player).filter(Player.season_id == season.id).all()
    ratings = _ratings_as_of_gw(db, season, playable, teams)
    fx_index = _index_team_fixtures(fixtures)
    fdr_index = _fixture_difficulty_index(fixtures, ratings)

    preds = _load_player_predictions(db, playable)
    projected = _project_player_points(
        players, teams, fx_index, ratings, preds, playable
    )
    profiles = _build_profiles(
        remaining_gws=list(range(playable, 39)),
        teams=teams,
        fx_index=fx_index,
        fdr_index=fdr_index,
        projected=projected,
        players=players,
        playable=playable,
        ratings=ratings,
    )
    return {
        "as_of_gameweek": playable,
        "notes": NOTES,
        "first_half": _half_payload("first", profiles, first_chips, playable),
        "second_half": _half_payload("second", profiles, second_chips, playable),
    }


def _empty_half(half: str, available: list[str]) -> dict:
    start, end = HALVES[half]
    return {
        "half": half,
        "start_gameweek": start,
        "end_gameweek": end,
        "remaining_gameweeks": [],
        "expired": True,
        "plan": [],
        "chips": [
            {
                "chip": chip,
                "chip_label": CHIP_LABELS[chip],
                "available": chip in available,
                "recommended_gameweek": None,
                "windows": [],
            }
            for chip in CHIP_IDS
        ],
    }


def _empty_payload(first_chips: list[str], second_chips: list[str]) -> dict:
    return {
        "as_of_gameweek": 1,
        "notes": NOTES,
        "first_half": _empty_half("first", first_chips),
        "second_half": _empty_half("second", second_chips),
    }


def _index_team_fixtures(fixtures: list[Fixture]) -> dict[tuple[int, int], list[Fixture]]:
    index: dict[tuple[int, int], list[Fixture]] = defaultdict(list)
    for fx in fixtures:
        if fx.gameweek_number is None:
            continue
        index[(fx.home_team_id, fx.gameweek_number)].append(fx)
        index[(fx.away_team_id, fx.gameweek_number)].append(fx)
    return index


def _team_fdr(fx: Fixture, team_id: int, ratings: dict[int, dict[str, float]]) -> float:
    outcomes = _fixture_outcomes(fx, ratings)
    is_home = fx.home_team_id == team_id
    if is_home:
        model = raw_difficulty_from_lambdas(outcomes["lam_home"], outcomes["lam_away"])
        fpl = fx.home_difficulty
    else:
        model = raw_difficulty_from_lambdas(outcomes["lam_away"], outcomes["lam_home"])
        fpl = fx.away_difficulty
    return blend_with_fpl_fdr(model, fpl)


def _fixture_difficulty_index(
    fixtures: list[Fixture], ratings: dict[int, dict[str, float]]
) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    for fx in fixtures:
        if fx.gameweek_number is None:
            continue
        out[(fx.home_team_id, fx.id)] = _team_fdr(fx, fx.home_team_id, ratings)
        out[(fx.away_team_id, fx.id)] = _team_fdr(fx, fx.away_team_id, ratings)
    return out


def _load_player_predictions(db: Session, playable: int) -> dict[tuple[int, int], float]:
    rows = (
        db.query(PredictionPlayerGameweek)
        .filter(PredictionPlayerGameweek.gameweek_number >= max(1, playable - 1))
        .all()
    )
    preferred = [r for r in rows if r.model_version == settings.model_version]
    use = preferred or rows
    out: dict[tuple[int, int], float] = {}
    for row in use:
        out[(row.player_id, row.gameweek_number)] = float(row.expected_points or 0.0)
    return out


def _scale_xpts(base_xpts: float, base_ctx: dict[str, float], ctx: dict[str, float]) -> float:
    if ctx["n_fixtures"] <= 0:
        return 0.0

    def _adj(c: dict[str, float]) -> float:
        lam_ratio = float(c.get("lam_for", 1.15)) / 1.15
        fdr = 1.12 - 0.14 * (c["opp_fdr"] - 3.0)
        home = 1.0 + 0.10 * c["is_home"]
        attack = max(0.50, min(1.55, lam_ratio))
        return max(0.35, fdr) * home * attack * max(c["n_fixtures"], 0.0)

    base_adj = _adj(base_ctx) if base_ctx["n_fixtures"] > 0 else 1.0
    return max(0.0, base_xpts * (_adj(ctx) / max(base_adj, 0.15)))


def _project_player_points(
    players: list[Player],
    teams: dict[int, Team],
    fx_index: dict[tuple[int, int], list[Fixture]],
    ratings: dict[int, dict[str, float]],
    preds: dict[tuple[int, int], float],
    playable: int,
) -> dict[tuple[int, int], float]:
    gws_with_preds = sorted({gw for (_pid, gw) in preds})
    anchor = playable if (playable in {gw for (_p, gw) in preds}) else None
    if anchor is None and gws_with_preds:
        future = [g for g in gws_with_preds if g >= playable]
        anchor = future[0] if future else gws_with_preds[-1]

    projected: dict[tuple[int, int], float] = dict(preds)
    for player in players:
        if not player.team_id:
            continue
        base_gw = anchor
        base_xpts = preds.get((player.id, base_gw), 0.0) if base_gw else 0.0
        if base_xpts <= 0:
            base_xpts = float(player.ep_next or 0.0)
            base_gw = playable
        if base_xpts <= 0:
            continue
        base_fx = fx_index.get((player.team_id, base_gw), []) if base_gw else []
        base_ctx = fixture_context(player, base_fx, ratings) or {
            "n_fixtures": 1.0,
            "opp_fdr": 3.0,
            "is_home": 0.5,
            "lam_for": 1.15,
        }
        for gw in range(playable, 39):
            key = (player.id, gw)
            if key in projected:
                continue
            gw_fx = fx_index.get((player.team_id, gw), [])
            ctx = fixture_context(player, gw_fx, ratings)
            if not ctx:
                projected[key] = 0.0
                continue
            projected[key] = _scale_xpts(base_xpts, base_ctx, ctx)
    return projected


def _opponent_labels(
    fixtures: list[Fixture], team_id: int, teams: dict[int, Team]
) -> str:
    parts: list[str] = []
    for fx in fixtures:
        is_home = fx.home_team_id == team_id
        opp = teams.get(fx.away_team_id if is_home else fx.home_team_id)
        short = opp.short_name if opp else "?"
        parts.append(f"{short} ({'H' if is_home else 'A'})")
    return ", ".join(parts) if parts else "Blank"


def _best_squad_xpts(by_pos: dict[str, list[float]], counts: dict[str, int]) -> float:
    total = 0.0
    for pos, n in counts.items():
        vals = sorted(by_pos.get(pos, []), reverse=True)[:n]
        total += sum(vals)
    return total


def _best_xi_xpts(by_pos: dict[str, list[float]]) -> float:
    return max(_best_squad_xpts(by_pos, option) for option in SQUAD_11_OPTIONS)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _captain_fixture_score(
    xp: float,
    lam_for: float,
    is_home: float,
    fdr: float,
    n_fixtures: int,
    position: str,
) -> float:
    dgw = 6.0 if n_fixtures >= 2 else 0.0
    pos_nudge = 0.8 if position == "FWD" else (0.35 if position == "MID" else 0.0)
    return (
        xp
        + 3.4 * lam_for
        + 1.4 * is_home
        - 0.7 * (fdr - 3.0)
        + dgw
        + pos_nudge
        + xp * 0.55 * max(0, n_fixtures - 1)
    )


def _make_captain_pick(
    player: Player,
    teams: dict[int, Team],
    fixtures: list[Fixture],
    xp: float,
    ctx: dict[str, float],
) -> CaptainPick:
    team = teams.get(player.team_id) if player.team_id else None
    display = _team_display(team)
    return CaptainPick(
        player_id=player.id,
        web_name=player.web_name,
        full_name=_full_name(player),
        team=display["team"],
        team_name=display["team_name"],
        team_code=display["team_code"],
        position=player.position,
        expected_points=xp,
        n_fixtures=len(fixtures),
        opponents=_opponent_labels(fixtures, player.team_id or -1, teams),
        is_home=ctx["is_home"] >= 0.5,
        expected_goals=round(float(ctx.get("lam_for", 0.0)), 2),
    )


def _pick_captain(
    players: list[Player],
    teams: dict[int, Team],
    fx_index: dict[tuple[int, int], list[Fixture]],
    ratings: dict[int, dict[str, float]],
    fdr_index: dict[tuple[int, int], float],
    projected: dict[tuple[int, int], float],
    gw: int,
) -> CaptainPick | None:
    best: CaptainPick | None = None
    best_score = -1.0
    for player in players:
        if player.position not in ("MID", "FWD"):
            continue
        xp = projected.get((player.id, gw), 0.0)
        if xp < 3.6:
            continue
        fxs = fx_index.get((player.team_id or -1, gw), [])
        if not fxs:
            continue
        ctx = fixture_context(player, fxs, ratings)
        if not ctx:
            continue
        model_fdrs = [fdr_index.get((player.team_id, fx.id), ctx["opp_fdr"]) for fx in fxs]
        score = _captain_fixture_score(
            xp,
            float(ctx.get("lam_for", 1.15)),
            float(ctx["is_home"]),
            _avg(model_fdrs) if model_fdrs else float(ctx["opp_fdr"]),
            len(fxs),
            player.position,
        )
        if score > best_score:
            best_score = score
            best = _make_captain_pick(player, teams, fxs, xp, ctx)
    return best


def _diversify_tc_windows(
    windows: list[ChipWindow], limit: int = WINDOW_LIMIT
) -> list[ChipWindow]:
    picked: list[ChipWindow] = []
    seen: set[int] = set()
    for window in windows:
        pid = window.player.player_id if window.player else None
        if pid is not None and pid in seen:
            continue
        picked.append(window)
        if pid is not None:
            seen.add(pid)
        if len(picked) >= limit:
            return picked
    if len(picked) < limit:
        for window in windows:
            if window in picked:
                continue
            picked.append(window)
            if len(picked) >= limit:
                break
    return picked


def _build_profiles(
    remaining_gws: list[int],
    teams: dict[int, Team],
    fx_index: dict[tuple[int, int], list[Fixture]],
    fdr_index: dict[tuple[int, int], float],
    projected: dict[tuple[int, int], float],
    players: list[Player],
    playable: int,
    ratings: dict[int, dict[str, float]],
) -> dict[int, GwProfile]:
    team_ids = list(teams.keys())
    gw_fdr: dict[int, float] = {}
    gw_easy: dict[int, int] = {}
    gw_blank: dict[int, int] = {}
    gw_double: dict[int, int] = {}
    gw_matches: dict[int, int] = {}

    for gw in range(1, 39):
        seen_fx: set[int] = set()
        fdrs: list[float] = []
        easy = 0
        blanks = 0
        doubles = 0
        for tid in team_ids:
            fxs = fx_index.get((tid, gw), [])
            if not fxs:
                blanks += 1
            elif len(fxs) >= 2:
                doubles += 1
            for fx in fxs:
                seen_fx.add(fx.id)
                score = fdr_index.get((tid, fx.id), 3.0)
                fdrs.append(score)
                if score <= 2.35:
                    easy += 1
        gw_matches[gw] = len(seen_fx)
        gw_fdr[gw] = _avg(fdrs) if fdrs else 3.0
        gw_easy[gw] = easy
        gw_blank[gw] = blanks
        gw_double[gw] = doubles

    profiles: dict[int, GwProfile] = {}
    for gw in remaining_gws:
        if gw_matches.get(gw, 0) == 0:
            continue
        by_pos: dict[str, list[float]] = defaultdict(list)
        for player in players:
            xp = projected.get((player.id, gw), 0.0)
            if xp <= 0.35:
                continue
            by_pos[player.position].append(xp)
        captain = _pick_captain(
            players, teams, fx_index, ratings, fdr_index, projected, gw
        )
        half_end = 19 if gw <= 19 else 38
        next_run = [g for g in range(gw, min(gw + 4, half_end + 1)) if g in gw_fdr]
        prior_run = [g for g in range(max(1, gw - 3), gw) if g in gw_fdr and gw_matches.get(g, 0)]
        next_avg = _avg([gw_fdr[g] for g in next_run])
        prior_avg = _avg([gw_fdr[g] for g in prior_run]) if prior_run else _avg(list(gw_fdr.values()))
        swing = prior_avg - next_avg
        easy_run_teams = 0
        for tid in team_ids:
            run_fdr: list[float] = []
            for g in next_run:
                for fx in fx_index.get((tid, g), []):
                    run_fdr.append(fdr_index.get((tid, fx.id), 3.0))
            if run_fdr and _avg(run_fdr) <= 2.45:
                easy_run_teams += 1
        upcoming_dgw = any(gw_double.get(g, 0) >= 3 for g in range(gw + 1, min(gw + 4, half_end + 1)))
        profiles[gw] = GwProfile(
            gameweek=gw,
            n_matches=gw_matches[gw],
            blank_teams=gw_blank[gw],
            double_teams=gw_double[gw],
            avg_fdr=gw_fdr[gw],
            easy_fixtures=gw_easy[gw],
            template_15_xpts=_best_squad_xpts(by_pos, SQUAD_15),
            template_11_xpts=_best_xi_xpts(by_pos),
            fixture_swing=swing,
            easy_run_teams=easy_run_teams,
            upcoming_dgw=upcoming_dgw,
            top_captain=captain,
            half_end=half_end,
            playable_start=playable,
        )
    return profiles


def _windows_for_chip(chip: str, profiles: list[GwProfile]) -> list[ChipWindow]:
    scored: list[ChipWindow] = []
    for profile in profiles:
        if chip == "wildcard":
            score = score_wildcard(profile)
            flags = _flags(profile)
            headline, reason, confidence = _wildcard_copy(profile, flags)
        elif chip == "bench_boost":
            score = score_bench_boost(profile)
            flags = _flags(profile)
            headline, reason, confidence = _bench_boost_copy(profile, flags)
        elif chip == "triple_captain":
            score = score_triple_captain(profile)
            flags = _flags(profile)
            headline, reason, confidence = _triple_captain_copy(profile, flags)
        else:
            score = score_free_hit(profile)
            flags = _flags(profile)
            headline, reason, confidence = _free_hit_copy(profile, flags)
        scored.append(
            ChipWindow(
                chip=chip,
                gameweek=profile.gameweek,
                score=score,
                confidence=confidence,
                headline=headline,
                reason=reason,
                flags=flags,
                player=profile.top_captain if chip == "triple_captain" else None,
            )
        )
    scored.sort(key=lambda w: (-w.score, w.gameweek))
    return scored


def _flags(profile: GwProfile) -> tuple[str, ...]:
    flags: list[str] = []
    if profile.double_teams >= 3:
        flags.append("dgw")
    if profile.blank_teams >= 4:
        flags.append("bgw")
    if profile.fixture_swing >= 0.18:
        flags.append("easier_run")
    if profile.upcoming_dgw:
        flags.append("dgw_soon")
    return tuple(flags)


def _wildcard_copy(profile: GwProfile, flags: tuple[str, ...]) -> tuple[str, str, str]:
    gw = profile.gameweek
    if "dgw_soon" in flags:
        headline = f"GW{gw} — rebuild before a double gameweek"
        reason = (
            f"Wildcard here to move into sides with easier upcoming fixtures "
            f"({profile.easy_run_teams} teams have a kind next-four run) and prepare for a double."
        )
        confidence = "high" if profile.easy_run_teams >= 4 else "medium"
    elif profile.fixture_swing >= 0.15:
        headline = f"GW{gw} — strongest fixture swing this half"
        reason = (
            f"The next four gameweeks look easier than the previous stretch "
            f"(swing {profile.fixture_swing:.2f}). Wildcard into those runs rather than chasing last week's form."
        )
        confidence = "high"
    else:
        headline = f"GW{gw} — useful week to reset"
        reason = (
            f"No dramatic blank/double yet. GW{gw} is a sensible reset: "
            f"{profile.easy_run_teams} teams have a relatively kind run, average FDR {profile.avg_fdr:.2f}."
        )
        confidence = "medium" if profile.easy_run_teams else "low"
    return headline, reason, confidence


def _bench_boost_copy(profile: GwProfile, flags: tuple[str, ...]) -> tuple[str, str, str]:
    gw = profile.gameweek
    if "dgw" in flags:
        headline = f"GW{gw} — {profile.double_teams} teams double"
        reason = (
            f"Bench Boost is strongest when 15 players can return points. "
            f"{profile.double_teams} sides have two fixtures and a projected 15-man haul of "
            f"{profile.template_15_xpts:.1f} xPts."
        )
        confidence = "high"
    elif profile.blank_teams:
        headline = f"GW{gw} — avoid if you can (blanks)"
        reason = (
            f"{profile.blank_teams} teams blank, so benches are more likely to miss. "
            f"Only consider BB here if your own 15 all play."
        )
        confidence = "low"
    else:
        headline = f"GW{gw} — highest 15-man coverage"
        reason = (
            f"No double gameweek is marked yet. This is the strongest single-fixture week "
            f"for a full 15 ({profile.template_15_xpts:.1f} projected xPts, {profile.easy_fixtures} easy slots)."
        )
        confidence = "medium"
    return headline, reason, confidence


def _triple_captain_copy(profile: GwProfile, flags: tuple[str, ...]) -> tuple[str, str, str]:
    gw = profile.gameweek
    cap = profile.top_captain
    if not cap:
        return f"GW{gw} — no captain candidate", "Need player projections for this week.", "low"
    venue = "at home" if cap.is_home else "away"
    xg_bit = (
        f" The attack projects {cap.expected_goals:.1f} xG." if cap.expected_goals else ""
    )
    if cap.n_fixtures >= 2:
        headline = f"GW{gw} — {cap.web_name} double ({cap.opponents})"
        reason = (
            f"{cap.web_name} ({cap.team}) plays twice: {cap.opponents}. "
            f"{cap.expected_points:.1f} xPts as captain, {cap.triple_expected_points:.1f} as TC.{xg_bit}"
        )
        confidence = "high"
    elif cap.is_home and cap.expected_goals >= 1.45:
        headline = f"GW{gw} — {cap.web_name} {venue} vs {cap.opponents}"
        reason = (
            f"{cap.web_name} ({cap.position}, {cap.team}) {venue} against {cap.opponents}.{xg_bit} "
            f"Projected {cap.expected_points:.1f} xPts, {cap.triple_expected_points:.1f} as Triple Captain "
            f"— a premium home fixture."
        )
        confidence = "high" if cap.expected_points >= 6.5 else "medium"
    elif not cap.is_home:
        headline = f"GW{gw} — {cap.web_name} away vs {cap.opponents}"
        reason = (
            f"{cap.web_name} ({cap.team}) travels ({cap.opponents}). "
            f"{cap.expected_points:.1f} xPts ({cap.triple_expected_points:.1f} TC).{xg_bit} "
            f"A home week is usually cleaner if you can wait."
        )
        confidence = "high" if cap.expected_points >= 7 else "medium"
    else:
        headline = f"GW{gw} — {cap.web_name} vs {cap.opponents}"
        reason = (
            f"Best captain week among remaining options: {cap.web_name} ({cap.position}, {cap.team}) "
            f"projects {cap.expected_points:.1f} xPts ({cap.triple_expected_points:.1f} as TC) "
            f"against {cap.opponents}.{xg_bit}"
        )
        confidence = "high" if cap.expected_points >= 7 else "medium"
    _ = flags
    return headline, reason, confidence


def _free_hit_copy(profile: GwProfile, flags: tuple[str, ...]) -> tuple[str, str, str]:
    gw = profile.gameweek
    if "bgw" in flags:
        headline = f"GW{gw} — {profile.blank_teams} teams blank"
        reason = (
            f"Free Hit is the chip for blanks: field a full XI from the sides that still play. "
            f"A constructed XI projects {profile.template_11_xpts:.1f} xPts this week."
        )
        confidence = "high"
    elif "dgw" in flags:
        headline = f"GW{gw} — better as a BB/TC week"
        reason = (
            "Several teams double, which is usually a Bench Boost or Triple Captain spot. "
            "Free Hit is weaker here unless your own squad is unusually poorly covered."
        )
        confidence = "low"
    else:
        headline = f"GW{gw} — one-week punt into easy fixtures"
        reason = (
            f"No blank gameweek is marked yet. This week offers the most concentrated easy fixtures "
            f"({profile.easy_fixtures}) for a throwaway XI ({profile.template_11_xpts:.1f} xPts)."
        )
        confidence = "medium"
    return headline, reason, confidence


def _half_payload(
    half: str,
    profiles: dict[int, GwProfile],
    available: list[str],
    playable: int,
) -> dict:
    start, end = HALVES[half]
    remaining = [gw for gw in range(max(playable, start), end + 1) if gw in profiles]
    expired = len(remaining) == 0
    half_profiles = [profiles[gw] for gw in remaining]
    windows_by_chip = {chip: _windows_for_chip(chip, half_profiles) for chip in CHIP_IDS}
    plan = [] if expired else assign_plan(windows_by_chip, available)
    plan_by_chip = {w.chip: w for w in plan}
    chips = []
    for chip in CHIP_IDS:
        rec = plan_by_chip.get(chip)
        ranked = windows_by_chip[chip]
        if chip == "triple_captain":
            pool = ranked
            if rec:
                pool = [rec, *[w for w in ranked if w.gameweek != rec.gameweek]]
            windows = _diversify_tc_windows(pool)
        else:
            windows = ranked[:WINDOW_LIMIT]
            if rec:
                rest = [w for w in windows if w.gameweek != rec.gameweek]
                windows = [rec, *rest][:WINDOW_LIMIT]
        chips.append(
            {
                "chip": chip,
                "chip_label": CHIP_LABELS[chip],
                "available": chip in available,
                "recommended_gameweek": rec.gameweek if rec else None,
                "windows": [w.as_dict() for w in windows],
            }
        )
    return {
        "half": half,
        "start_gameweek": start,
        "end_gameweek": end,
        "remaining_gameweeks": remaining,
        "expired": expired,
        "plan": [w.as_dict() for w in plan],
        "chips": chips,
    }
