"""player market fields

Revision ID: 002
Revises: 001
Create Date: 2026-09-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.add_column(sa.Column("first_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("second_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("transfers_in_event", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("transfers_out_event", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("cost_change_event", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.drop_column("cost_change_event")
        batch_op.drop_column("transfers_out_event")
        batch_op.drop_column("transfers_in_event")
        batch_op.drop_column("second_name")
        batch_op.drop_column("first_name")
