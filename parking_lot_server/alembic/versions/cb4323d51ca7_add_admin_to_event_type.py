"""add admin to event_type

Revision ID: cb4323d51ca7
Revises: 84f9f0fb12fe
Create Date: 2026-05-08 10:12:04.493018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb4323d51ca7'
down_revision: Union[str, Sequence[str], None] = '84f9f0fb12fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_event_type", "entry_exit_logs", type_="check")
    op.create_check_constraint(
        "ck_event_type",
        "entry_exit_logs",
        "event_type IN ('entry', 'exit', 'admin')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "entry_exit_logs", type_="check")
    op.create_check_constraint(
        "ck_event_type",
        "entry_exit_logs",
        "event_type IN ('entry', 'exit')",
    )
