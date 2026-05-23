"""add_lat_lng_to_parking_lots

Revision ID: f3a1b8c2d940
Revises: ca3ed5b9fa78
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a1b8c2d940'
down_revision: Union[str, Sequence[str], None] = 'ca3ed5b9fa78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('parking_lots', sa.Column('latitude', sa.Double(), nullable=False, server_default='0'))
    op.add_column('parking_lots', sa.Column('longitude', sa.Double(), nullable=False, server_default='0'))
    op.alter_column('parking_lots', 'latitude', server_default=None)
    op.alter_column('parking_lots', 'longitude', server_default=None)
    op.alter_column('parking_lots', 'address', nullable=False)


def downgrade() -> None:
    op.drop_column('parking_lots', 'latitude')
    op.drop_column('parking_lots', 'longitude')
    op.alter_column('parking_lots', 'address', nullable=True)
