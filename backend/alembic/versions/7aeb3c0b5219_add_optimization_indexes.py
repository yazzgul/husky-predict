"""add_optimization_indexes

Revision ID: 7aeb3c0b5219
Revises: 761b470c39de
Create Date: 2026-02-07 19:19:55.748359

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7aeb3c0b5219'
down_revision: Union[str, Sequence[str], None] = '761b470c39de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавление индексов для оптимизации производительности

    Эти индексы критически важны для:
    - Быстрого поиска собак по различным критериям
    - Оптимизации join операций
    - Предотвращения дубликатов в связных таблицах
    - Ускорения запросов к владельцам и заводчикам
    """

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ DOG
    # ========================================================================

    # Индекс для поиска по имени (case-insensitive)
    # Используется при поиске собак по имени
    op.create_index(
        'ix_dog_registered_name_lower',
        'dog',
        [sa.text('LOWER(registered_name)')],
        unique=False
    )

    # Составной индекс для поиска по имени и полу
    # Используется в функции find_existing_dog
    op.create_index(
        'ix_dog_name_sex',
        'dog',
        ['registered_name', 'sex'],
        unique=False
    )

    # Индекс для поиска по дате рождения
    # Используется при фильтрации и сортировке
    op.create_index(
        'ix_dog_date_of_birth',
        'dog',
        ['date_of_birth'],
        unique=False
    )

    # Составной индекс для поиска детей пары родителей
    # Используется при построении родословных
    op.create_index(
        'ix_dog_parents',
        'dog',
        ['dam_id', 'sire_id'],
        unique=False,
        postgresql_where=sa.text('dam_id IS NOT NULL OR sire_id IS NOT NULL')
    )

    # Индекс для поиска по birth_litter_id
    # Используется при работе с пометами
    op.create_index(
        'ix_dog_birth_litter_id',
        'dog',
        ['birth_litter_id'],
        unique=False,
        postgresql_where=sa.text('birth_litter_id IS NOT NULL')
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ OWNER
    # ========================================================================

    # Индекс для поиска владельцев по имени (case-insensitive)
    op.create_index(
        'ix_owner_name_lower',
        'owner',
        [sa.text('LOWER(name)')],
        unique=False
    )

    # Индекс для поиска по питомнику
    op.create_index(
        'ix_owner_kennel',
        'owner',
        ['kennel'],
        unique=False,
        postgresql_where=sa.text('kennel IS NOT NULL')
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ BREEDER
    # ========================================================================

    # Индекс для поиска заводчиков по имени (case-insensitive)
    op.create_index(
        'ix_breeder_name_lower',
        'breeder',
        [sa.text('LOWER(name)')],
        unique=False
    )

    # Индекс для поиска по питомнику
    op.create_index(
        'ix_breeder_kennel',
        'breeder',
        ['kennel'],
        unique=False,
        postgresql_where=sa.text('kennel IS NOT NULL')
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ TITLE
    # ========================================================================

    # Индекс для поиска титулов конкретной собаки
    # КРИТИЧЕСКИ ВАЖЕН для функции save_dog_titles
    op.create_index(
        'ix_title_dog_id',
        'title',
        ['dog_id'],
        unique=False
    )

    # Составной индекс для проверки существования титула
    # Используется при сохранении титулов (добавлено: учитывать страну, ведь титул бывает в разных странах)
    # В будущем: добавить год титула (на сайте зоопортал не пишется в данный момент)
    op.create_index(
        'ix_title_dog_short_name',
        'title',
        # ['dog_id', 'short_name'],
        ['dog_id', 'short_name', 'country'],
        unique=False
    )

    # УНИКАЛЬНЫЙ индекс для предотвращения дубликатов титулов
    # Собака не может иметь два одинаковых титула
    op.create_index(
        'ix_title_unique',
        'title',
        # ['dog_id', 'short_name'],
        ['dog_id', 'short_name', 'country'],
        unique=True
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ DOGBREEDERLINK
    # ========================================================================

    # Индекс для быстрого поиска заводчиков собаки
    op.create_index(
        'ix_dogbreederlink_dog_id',
        'dogbreederlink',
        ['dog_id'],
        unique=False
    )

    # Индекс для быстрого поиска собак заводчика
    op.create_index(
        'ix_dogbreederlink_breeder_id',
        'dogbreederlink',
        ['breeder_id'],
        unique=False
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ DOGOWNERLINK
    # ========================================================================

    # Индекс для быстрого поиска владельцев собаки
    op.create_index(
        'ix_dogownerlink_dog_id',
        'dogownerlink',
        ['dog_id'],
        unique=False
    )

    # Индекс для быстрого поиска собак владельца
    op.create_index(
        'ix_dogownerlink_owner_id',
        'dogownerlink',
        ['owner_id'],
        unique=False
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ DOGSIBLINGLINK
    # ========================================================================

    # Индекс для быстрого поиска сиблингов собаки
    op.create_index(
        'ix_dogsiblinglink_dog_id',
        'dogsiblinglink',
        ['dog_id'],
        unique=False
    )

    # Индекс для обратного поиска
    op.create_index(
        'ix_dogsiblinglink_sibling_id',
        'dogsiblinglink',
        ['sibling_id'],
        unique=False
    )

    # ========================================================================
    # ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ LITTER
    # ========================================================================

    # Индекс для поиска пометов по отцу
    op.create_index(
        'ix_litter_sire_id',
        'litter',
        ['sire_id'],
        unique=False,
        postgresql_where=sa.text('sire_id IS NOT NULL')
    )

    # Индекс для поиска пометов по матери
    op.create_index(
        'ix_litter_dam_id',
        'litter',
        ['dam_id'],
        unique=False,
        postgresql_where=sa.text('dam_id IS NOT NULL')
    )

    # Составной индекс для поиска пометов конкретной пары
    op.create_index(
        'ix_litter_parents',
        'litter',
        ['sire_id', 'dam_id'],
        unique=False,
        postgresql_where=sa.text('sire_id IS NOT NULL AND dam_id IS NOT NULL')
    )

    # Индекс для поиска пометов по дате
    op.create_index(
        'ix_litter_date_of_birth',
        'litter',
        ['date_of_birth'],
        unique=False,
        postgresql_where=sa.text('date_of_birth IS NOT NULL')
    )


def downgrade() -> None:
    """
    Удаление индексов при откате миграции
    """

    # LITTER
    op.drop_index('ix_litter_date_of_birth', table_name='litter')
    op.drop_index('ix_litter_parents', table_name='litter')
    op.drop_index('ix_litter_dam_id', table_name='litter')
    op.drop_index('ix_litter_sire_id', table_name='litter')

    # DOGSIBLINGLINK
    op.drop_index('ix_dogsiblinglink_sibling_id', table_name='dogsiblinglink')
    op.drop_index('ix_dogsiblinglink_dog_id', table_name='dogsiblinglink')

    # DOGOWNERLINK
    op.drop_index('ix_dogownerlink_owner_id', table_name='dogownerlink')
    op.drop_index('ix_dogownerlink_dog_id', table_name='dogownerlink')

    # DOGBREEDERLINK
    op.drop_index('ix_dogbreederlink_breeder_id', table_name='dogbreederlink')
    op.drop_index('ix_dogbreederlink_dog_id', table_name='dogbreederlink')

    # TITLE
    op.drop_index('ix_title_unique', table_name='title')
    op.drop_index('ix_title_dog_short_name', table_name='title')
    op.drop_index('ix_title_dog_id', table_name='title')

    # BREEDER
    op.drop_index('ix_breeder_kennel', table_name='breeder')
    op.drop_index('ix_breeder_name_lower', table_name='breeder')

    # OWNER
    op.drop_index('ix_owner_kennel', table_name='owner')
    op.drop_index('ix_owner_name_lower', table_name='owner')

    # DOG
    op.drop_index('ix_dog_birth_litter_id', table_name='dog')
    op.drop_index('ix_dog_parents', table_name='dog')
    op.drop_index('ix_dog_date_of_birth', table_name='dog')
    op.drop_index('ix_dog_name_sex', table_name='dog')
    op.drop_index('ix_dog_registered_name_lower', table_name='dog')