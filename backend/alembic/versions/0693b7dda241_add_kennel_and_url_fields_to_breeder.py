"""add_kennel_and_url_fields_to_breeder

Revision ID: 0693b7dda241
Revises: 72fc22881f8d
Create Date: 2026-02-04 21:15:05.968390

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0693b7dda241'
down_revision: Union[str, Sequence[str], None] = '72fc22881f8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('breeder', sa.Column('kennel', sa.String(), nullable=True))
    op.add_column('breeder', sa.Column('breeder_url', sa.String(), nullable=True))
    op.add_column('breeder', sa.Column('kennel_url', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('breeder', 'kennel_url')
    op.drop_column('breeder', 'breeder_url')
    op.drop_column('breeder', 'kennel')