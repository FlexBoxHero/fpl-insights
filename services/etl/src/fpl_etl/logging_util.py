from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fpl_shared.models import EtlRun


def record_etl_run(db: Session, job_name: str, status: str, message: str | None = None) -> None:
    db.rollback()
    db.add(
        EtlRun(
            job_name=job_name,
            status=status,
            message=message,
            finished_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
