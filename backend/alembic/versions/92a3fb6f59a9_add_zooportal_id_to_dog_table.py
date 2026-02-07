"""add zooportal_id to dog table

Revision ID: 92a3fb6f59a9
Revises: 60ba853299dc
Create Date: 2025-12-23 19:12:03.966670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92a3fb6f59a9'
down_revision: Union[str, Sequence[str], None] = '60ba853299dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем колонку zooportal_id в таблицу dog
    op.add_column('dog',
        sa.Column('zooportal_id', sa.String(), nullable=True)
    )

    # Создаем индекс для быстрого поиска по zooportal_id
    op.create_index(op.f('ix_dog_zooportal_id'), 'dog', ['zooportal_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем индекс
    op.drop_index(op.f('ix_dog_zooportal_id'), table_name='dog')

    # Удаляем колонку
    op.drop_column('dog', 'zooportal_id')
