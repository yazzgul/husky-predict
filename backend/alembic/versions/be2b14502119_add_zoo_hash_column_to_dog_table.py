"""add zoo_hash column to dog table

Revision ID: be2b14502119
Revises: 92a3fb6f59a9
Create Date: 2026-02-04 16:38:32.761603

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be2b14502119'
down_revision: Union[str, Sequence[str], None] = '92a3fb6f59a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # добавляем поле без заполнения данных
    op.add_column('dog', sa.Column('zoo_hash', sa.String(64), nullable=True))

    # Создаем индекс
    op.create_index(op.f('ix_dog_zoo_hash'), 'dog', ['zoo_hash'])

    # добавим уникальное ограничение позже, когда все записи будут заполнены
    # op.create_unique_constraint('uq_dogs_zoo_hash', 'dog', ['zoo_hash'])

    op.execute(
        "COMMENT ON COLUMN dog.zoo_hash IS 'Unique hash for dog identification across systems'")


def downgrade() -> None:
    # Удаляем комментарий (если есть)
    op.execute("COMMENT ON COLUMN dog.zoo_hash IS NULL")

    # Удаляем индекс и поле
    op.drop_index(op.f('ix_dog_zoo_hash'), table_name='dog')
    op.drop_column('dog', 'zoo_hash')