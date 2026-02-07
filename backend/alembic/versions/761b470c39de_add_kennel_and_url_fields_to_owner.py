"""add_kennel_and_url_fields_to_owner

Revision ID: 761b470c39de
Revises: 0693b7dda241
Create Date: 2026-02-04 21:15:19.549065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '761b470c39de'
down_revision: Union[str, Sequence[str], None] = '0693b7dda241'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('owner', sa.Column('kennel', sa.String(), nullable=True))
    op.add_column('owner', sa.Column('owner_url', sa.String(), nullable=True))
    op.add_column('owner', sa.Column('kennel_url', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('owner', 'kennel_url')
    op.drop_column('owner', 'owner_url')
    op.drop_column('owner', 'kennel')
