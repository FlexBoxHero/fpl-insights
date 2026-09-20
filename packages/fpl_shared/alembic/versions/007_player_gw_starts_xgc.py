"""player-gameweek starts and expected goals conceded

Revision ID: 007
Revises: 006
Create Date: 2026-09-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_gameweek_stats") as batch_op:
        batch_op.add_column(
            sa.Column("starts", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "expected_goals_conceded",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("player_gameweek_stats") as batch_op:
        batch_op.drop_column("expected_goals_conceded")
        batch_op.drop_column("starts")
