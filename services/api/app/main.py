import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import insights_service
from app.chip_strategy import build_chip_strategy, parse_chips
from app.player_watch import player_watch
from app.schemas import (
    BonusOutlookOut,
    CaptainPickOut,
    ChipStrategyOut,
    DeadlineOut,
    DefensiveContribOut,
    FixtureOut,
    GameweekOut,
    HomeDashboardOut,
    ModelMetaOut,
    PlayerPredictionOut,
    PlayerSeasonStatOut,
    PlayerWatchOut,
    SquadAnalysisIn,
    SquadScreenshotIn,
    SquadVisionStatusOut,
    TeamFixtureRunOut,
    TeamMetricRunOut,
    TeamOutlookRowOut,
    TeamPredictionOut,
)
from app.squad_analysis import (
    analyze_from_entry,
    analyze_squad,
    parse_screenshot,
    vision_enabled,
)
from fpl_shared.config import REPO_ROOT, settings
from fpl_shared.db import get_db
from fpl_shared.models import (
    EtlRun,
    Fixture,
    Gameweek,
    Player,
    PredictionPlayerGameweek,
    PredictionTeamFixture,
    Season,
    Team,
)

app = FastAPI(title="FPL Insights API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _current_season(db: Session) -> Season | None:
    return db.query(Season).filter(Season.is_current.is_(True)).first()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/gameweeks", response_model=list[GameweekOut])
def list_gameweeks(db: Session = Depends(get_db)) -> list[GameweekOut]:
    season = _current_season(db)
    if not season:
        season = db.query(Season).order_by(Season.id.desc()).first()
    if not season:
        return []
    gws = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id)
        .order_by(Gameweek.number)
        .all()
    )
    kickoffs = {
        number: (first, last)
        for number, first, last in (
            db.query(
                Fixture.gameweek_number,
                func.min(Fixture.kickoff_time),
                func.max(Fixture.kickoff_time),
            )
            .filter(
                Fixture.season_id == season.id,
                Fixture.gameweek_number.isnot(None),
                Fixture.kickoff_time.isnot(None),
            )
            .group_by(Fixture.gameweek_number)
            .all()
        )
    }
    return [
        GameweekOut(
            id=gw.id,
            number=gw.number,
            name=gw.name,
            finished=gw.finished,
            is_current=gw.is_current,
            is_next=gw.is_next,
            deadline_time=gw.deadline_time,
            first_kickoff=kickoffs.get(gw.number, (None, None))[0],
            last_kickoff=kickoffs.get(gw.number, (None, None))[1],
        )
        for gw in gws
    ]


@app.get("/v1/fixtures", response_model=list[FixtureOut])
def list_fixtures(
    gameweek: int = Query(..., ge=1, le=38),
    db: Session = Depends(get_db),
) -> list[FixtureOut]:
    season = _current_season(db) or db.query(Season).order_by(Season.id.desc()).first()
    if not season:
        return []
    teams = {t.id: t for t in db.query(Team).filter(Team.season_id == season.id).all()}
    fixtures = (
        db.query(Fixture)
        .filter(Fixture.season_id == season.id, Fixture.gameweek_number == gameweek)
        .order_by(Fixture.kickoff_time)
        .all()
    )
    out: list[FixtureOut] = []
    for fx in fixtures:
        home = teams.get(fx.home_team_id)
        away = teams.get(fx.away_team_id)
        out.append(
            FixtureOut(
                id=fx.id,
                gameweek_number=fx.gameweek_number,
                home_team=home.name if home else "Home",
                away_team=away.name if away else "Away",
                kickoff_time=fx.kickoff_time,
                finished=fx.finished,
                home_score=fx.home_score,
                away_score=fx.away_score,
            )
        )
    return out


@app.get("/v1/predictions/teams", response_model=list[TeamPredictionOut])
def team_predictions(
    gameweek: int = Query(..., ge=1, le=38),
    db: Session = Depends(get_db),
) -> list[TeamPredictionOut]:
    preds = (
        db.query(PredictionTeamFixture)
        .filter(PredictionTeamFixture.gameweek_number == gameweek)
        .all()
    )
    if not preds:
        return []
    fixture_ids = [p.fixture_id for p in preds]
    fixtures = {f.id: f for f in db.query(Fixture).filter(Fixture.id.in_(fixture_ids)).all()}
    team_ids = set()
    for f in fixtures.values():
        team_ids.add(f.home_team_id)
        team_ids.add(f.away_team_id)
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    out: list[TeamPredictionOut] = []
    for p in preds:
        fx = fixtures.get(p.fixture_id)
        if not fx:
            continue
        home = teams.get(fx.home_team_id)
        away = teams.get(fx.away_team_id)
        out.append(
            TeamPredictionOut(
                fixture_id=fx.id,
                gameweek_number=gameweek,
                home_team=home.name if home else "Home",
                away_team=away.name if away else "Away",
                kickoff_time=fx.kickoff_time,
                home_win_prob=p.home_win_prob,
                draw_prob=p.draw_prob,
                away_win_prob=p.away_win_prob,
                home_clean_sheet_prob=p.home_clean_sheet_prob,
                away_clean_sheet_prob=p.away_clean_sheet_prob,
                home_score_prob=p.home_score_prob,
                away_score_prob=p.away_score_prob,
            )
        )
    return sorted(out, key=lambda x: x.kickoff_time or x.fixture_id)


@app.get("/v1/predictions/players", response_model=list[PlayerPredictionOut])
def player_predictions(
    gameweek: int = Query(..., ge=1, le=38),
    team_id: int | None = None,
    position: str | None = None,
    db: Session = Depends(get_db),
) -> list[PlayerPredictionOut]:
    q = db.query(PredictionPlayerGameweek).filter(
        PredictionPlayerGameweek.gameweek_number == gameweek
    )
    preds = q.all()
    if not preds:
        return []
    player_ids = [p.player_id for p in preds]
    players = {pl.id: pl for pl in db.query(Player).filter(Player.id.in_(player_ids)).all()}
    team_ids = {pl.team_id for pl in players.values() if pl.team_id}
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    season_id = next(iter(players.values())).season_id if players else None
    gw_fixtures: list[Fixture] = []
    if season_id is not None:
        gw_fixtures = (
            db.query(Fixture)
            .filter(Fixture.season_id == season_id, Fixture.gameweek_number == gameweek)
            .all()
        )
    fx_by_team = insights_service.fixtures_by_team(gw_fixtures)
    out: list[PlayerPredictionOut] = []
    for p in preds:
        pl = players.get(p.player_id)
        if not pl:
            continue
        if team_id is not None and pl.team_id != team_id:
            continue
        if position and pl.position.upper() != position.upper():
            continue
        team = teams.get(pl.team_id) if pl.team_id else None
        full_name = (
            f"{pl.first_name} {pl.second_name}".strip()
            if pl.first_name and pl.second_name
            else pl.web_name
        )
        opp = insights_service.opponent_summary(
            fx_by_team.get(pl.team_id, []) if pl.team_id else [],
            pl.team_id or -1,
            teams,
        )
        out.append(
            PlayerPredictionOut(
                player_id=pl.id,
                fpl_element_id=pl.fpl_element_id,
                web_name=pl.web_name,
                full_name=full_name,
                **insights_service._team_display(team),
                position=pl.position,
                price=pl.now_cost / 10.0,
                gameweek_number=gameweek,
                expected_points=p.expected_points,
                baseline_last_gw=p.baseline_last_gw,
                baseline_ep_next=p.baseline_ep_next,
                **opp,
            )
        )
    return sorted(out, key=lambda x: -x.expected_points)


@app.get("/v1/insights/team-fixture-runs", response_model=list[TeamFixtureRunOut])
def team_fixture_runs(
    start_gameweek: int = Query(..., ge=1, le=38),
    fixture_count: int = Query(5, ge=3, le=8),
    db: Session = Depends(get_db),
) -> list[TeamFixtureRunOut]:
    return insights_service.team_fixture_runs(db, start_gameweek, fixture_count)


@app.get("/v1/insights/team-clean-sheets", response_model=list[TeamMetricRunOut])
def team_clean_sheets(
    start_gameweek: int = Query(..., ge=1, le=38),
    gameweek_count: int = Query(3, ge=3, le=8),
    db: Session = Depends(get_db),
) -> list[TeamMetricRunOut]:
    return insights_service.team_clean_sheet_runs(db, start_gameweek, gameweek_count)


@app.get("/v1/insights/team-goals", response_model=list[TeamMetricRunOut])
def team_goals(
    start_gameweek: int = Query(..., ge=1, le=38),
    gameweek_count: int = Query(3, ge=3, le=8),
    db: Session = Depends(get_db),
) -> list[TeamMetricRunOut]:
    return insights_service.team_goals_runs(db, start_gameweek, gameweek_count)


@app.get("/v1/insights/captain", response_model=list[CaptainPickOut])
def captain_insights(
    gameweek: int = Query(..., ge=1, le=38),
    db: Session = Depends(get_db),
) -> list[CaptainPickOut]:
    return insights_service.captain_picks(db, gameweek)


@app.get("/v1/insights/player-watch", response_model=PlayerWatchOut)
def player_watch_insights(db: Session = Depends(get_db)) -> PlayerWatchOut:
    return PlayerWatchOut(**player_watch(db))


@app.get("/v1/insights/defensive-contributions", response_model=list[DefensiveContribOut])
def defensive_contributions(
    gameweek: int = Query(..., ge=1, le=38),
    db: Session = Depends(get_db),
) -> list[DefensiveContribOut]:
    return insights_service.defensive_contribution_outlook(db, gameweek)


@app.get("/v1/insights/bonus", response_model=list[BonusOutlookOut])
def bonus_insights(
    gameweek: int = Query(..., ge=1, le=38),
    db: Session = Depends(get_db),
) -> list[BonusOutlookOut]:
    return insights_service.bonus_points_outlook(db, gameweek)


@app.get("/v1/insights/chip-strategy", response_model=ChipStrategyOut)
def chip_strategy(
    first_chips: str | None = Query(
        None,
        description="Comma-separated chips still available in GW1–19",
    ),
    second_chips: str | None = Query(
        None,
        description="Comma-separated chips still available in GW20–38",
    ),
    db: Session = Depends(get_db),
) -> ChipStrategyOut:
    data = build_chip_strategy(
        db,
        parse_chips(first_chips),
        parse_chips(second_chips),
    )
    return ChipStrategyOut(**data)


@app.post("/v1/insights/squad-analysis")
def squad_analysis(body: SquadAnalysisIn, db: Session = Depends(get_db)) -> dict:
    try:
        return analyze_squad(
            db,
            [p.model_dump() for p in body.picks],
            bank=body.bank,
            free_transfers=body.free_transfers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/insights/squad-analysis/from-entry")
def squad_analysis_from_entry(
    entry_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return analyze_from_entry(db, entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/insights/squad-vision-status", response_model=SquadVisionStatusOut)
def squad_vision_status() -> SquadVisionStatusOut:
    return SquadVisionStatusOut(enabled=vision_enabled())


@app.post("/v1/insights/squad-from-screenshot")
def squad_from_screenshot(body: SquadScreenshotIn, db: Session = Depends(get_db)) -> dict:
    try:
        return parse_screenshot(db, body.image_base64, body.media_type)
    except PermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read screenshot: {exc}") from exc


@app.get("/v1/dashboard/home", response_model=HomeDashboardOut)
def home_dashboard(
    gameweek: int | None = Query(None, ge=1, le=38),
    db: Session = Depends(get_db),
) -> HomeDashboardOut:
    data = insights_service.home_dashboard(db, gameweek)
    return HomeDashboardOut(**data)


@app.get("/v1/players/season-stats", response_model=list[PlayerSeasonStatOut])
def player_season_stats(
    gameweek: int | None = Query(None, ge=1, le=38),
    position: str | None = None,
    min_minutes: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[PlayerSeasonStatOut]:
    return insights_service.player_season_stats(db, gameweek, position, min_minutes, limit)


@app.get("/v1/meta/deadline", response_model=DeadlineOut)
def transfer_deadline(db: Session = Depends(get_db)) -> DeadlineOut:
    return DeadlineOut(
        deadline_time=insights_service.next_deadline(db),
        server_time=datetime.now(timezone.utc),
    )


@app.get("/v1/meta/model-version", response_model=ModelMetaOut)
def model_meta(db: Session = Depends(get_db)) -> ModelMetaOut:
    last = db.query(EtlRun).order_by(EtlRun.finished_at.desc()).first()
    return ModelMetaOut(
        model_version=settings.model_version,
        last_etl_at=last.finished_at if last else None,
        last_etl_job=last.job_name if last else None,
        last_etl_status=last.status if last else None,
    )


SPA_DIR = Path(os.environ.get("SPA_DIR", REPO_ROOT / "apps" / "web" / "dist" / "web" / "browser"))


def spa_response(full_path: str) -> FileResponse:
    """Serve a built SPA file when it exists; otherwise index.html for Angular routes."""
    spa_root = SPA_DIR.resolve()
    index = spa_root / "index.html"
    if not spa_root.is_dir() or not index.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    requested = (spa_root / full_path).resolve()
    if not requested.is_relative_to(spa_root):
        raise HTTPException(status_code=404, detail="Not Found")
    if requested.is_file():
        return FileResponse(requested)
    return FileResponse(index)


def build_server() -> FastAPI:
    """Public process: /api/* plus the Angular SPA when a production build exists."""
    server = FastAPI(title="FPL Insights", version="0.1.0")
    server.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @server.get("/health")
    def root_health() -> dict[str, str]:
        return {"status": "ok"}

    server.mount("/api", app)

    @server.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    def spa_fallback(full_path: str) -> FileResponse:
        return spa_response(full_path)

    return server


server = build_server()
