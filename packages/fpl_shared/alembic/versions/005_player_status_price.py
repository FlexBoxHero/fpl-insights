"""player status, discipline, and price-change fields

Revision ID: 005
Revises: 004
Create Date: 2026-09-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=8), nullable=False, server_default="a"))
        batch_op.add_column(sa.Column("news", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("news_added", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("chance_of_playing_this_round", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("chance_of_playing_next_round", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("yellow_cards", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("red_cards", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("price_change_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("price_change_projected_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("price_change_likelihood", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("price_change_calibrating", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.drop_column("price_change_calibrating")
        batch_op.drop_column("price_change_likelihood")
        batch_op.drop_column("price_change_projected_percent")
        batch_op.drop_column("price_change_percent")
        batch_op.drop_column("red_cards")
        batch_op.drop_column("yellow_cards")
        batch_op.drop_column("chance_of_playing_next_round")
        batch_op.drop_column("chance_of_playing_this_round")
        batch_op.drop_column("news_added")
        batch_op.drop_column("news")
        batch_op.drop_column("status")
