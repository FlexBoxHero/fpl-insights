from sqlalchemy.orm import Session

from fpl_ml.player_model import predict_players_for_gw
from fpl_ml.team_model import predict_team_fixtures_for_gw
from fpl_shared.models import Gameweek, Season


def default_target_gameweek(db: Session) -> int:
    season = db.query(Season).filter(Season.is_current.is_(True)).first()
    if not season:
        return 1
    nxt = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.is_next.is_(True))
        .first()
    )
    if nxt:
        return nxt.number
    cur = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.is_current.is_(True))
        .first()
    )
    if cur:
        return cur.number + 1
    unfinished = (
        db.query(Gameweek)
        .filter(Gameweek.season_id == season.id, Gameweek.finished.is_(False))
        .order_by(Gameweek.number)
        .first()
    )
    return unfinished.number if unfinished else 1


def run_all_predictions(db: Session, gameweek: int | None = None) -> dict[str, int]:
    gw = gameweek or default_target_gameweek(db)
    team_n = predict_team_fixtures_for_gw(db, gw)
    player_n = predict_players_for_gw(db, gw)
    return {"gameweek": gw, "team_predictions": team_n, "player_predictions": player_n}
