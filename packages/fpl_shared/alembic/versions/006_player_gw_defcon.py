"""player-gameweek defensive contribution components (CBI, tackles, recoveries)

Revision ID: 006
Revises: 005
Create Date: 2026-09-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_gameweek_stats") as batch_op:
        batch_op.add_column(
            sa.Column(
                "clearances_blocks_interceptions",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("tackles", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("recoveries", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "defensive_contribution",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("player_gameweek_stats") as batch_op:
        batch_op.drop_column("defensive_contribution")
        batch_op.drop_column("recoveries")
        batch_op.drop_column("tackles")
        batch_op.drop_column("clearances_blocks_interceptions")
