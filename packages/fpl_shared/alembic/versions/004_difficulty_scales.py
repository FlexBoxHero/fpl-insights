"""weekly FDR difficulty scale

Revision ID: 004
Revises: 003
Create Date: 2026-09-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "difficulty_scales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("as_of_gameweek", sa.Integer(), nullable=False),
        sa.Column("break_p20", sa.Float(), nullable=False),
        sa.Column("break_p40", sa.Float(), nullable=False),
        sa.Column("break_p60", sa.Float(), nullable=False),
        sa.Column("break_p80", sa.Float(), nullable=False),
        sa.Column("score_min", sa.Float(), nullable=False),
        sa.Column("score_max", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "as_of_gameweek", name="uq_diff_scale_gw"),
    )
    op.create_index("ix_difficulty_scales_season_id", "difficulty_scales", ["season_id"])


def downgrade() -> None:
    op.drop_index("ix_difficulty_scales_season_id", table_name="difficulty_scales")
    op.drop_table("difficulty_scales")
