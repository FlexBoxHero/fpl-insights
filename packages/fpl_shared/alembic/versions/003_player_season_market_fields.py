"""player season market fields

Revision ID: 003
Revises: 002
Create Date: 2026-09-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.add_column(sa.Column("transfers_in", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("transfers_out", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("cost_change_start", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.drop_column("cost_change_start")
        batch_op.drop_column("transfers_out")
        batch_op.drop_column("transfers_in")
