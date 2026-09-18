from sqlalchemy.orm import Session

from fpl_shared.models import TeamNameAlias
from fpl_shared.team_aliases import DEFAULT_ALIASES


def seed_team_aliases(db: Session) -> int:
    count = 0
    for short, fd_name in DEFAULT_ALIASES.items():
        existing = db.query(TeamNameAlias).filter(TeamNameAlias.fpl_short_name == short).first()
        if existing:
            existing.football_data_name = fd_name
        else:
            db.add(TeamNameAlias(fpl_short_name=short, football_data_name=fd_name))
            count += 1
    db.commit()
    return count
