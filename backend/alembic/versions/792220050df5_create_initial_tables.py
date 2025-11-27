"""create initial tables

Revision ID: 60ba853299dc
Revises:
Create Date: 2025-10-02 15:37:11.456679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60ba853299dc'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Сначала создаем простые таблицы без внешних ключей
    op.create_table('breeder',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_breeder', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_breeder_uuid'), 'breeder', ['uuid'], unique=True)

    op.create_table('owner',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_main_owner', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_owner_uuid'), 'owner', ['uuid'], unique=True)

    # 2. Создаем таблицу dog БЕЗ внешних ключей на litter
    op.create_table('dog',
        sa.Column('uuid', sa.String(), nullable=False),
        sa.Column('registered_name', sa.String(), nullable=True),
        sa.Column('call_name', sa.String(), nullable=True),
        sa.Column('link_name', sa.String(), nullable=True),
        sa.Column('sex', sa.Integer(), nullable=False),
        sa.Column('year_of_birth', sa.Integer(), nullable=True),
        sa.Column('month_of_birth', sa.Integer(), nullable=True),
        sa.Column('day_of_birth', sa.Integer(), nullable=True),
        sa.Column('date_of_birth', sa.DateTime(), nullable=True),
        sa.Column('year_of_death', sa.Integer(), nullable=True),
        sa.Column('month_of_death', sa.Integer(), nullable=True),
        sa.Column('day_of_death', sa.Integer(), nullable=True),
        sa.Column('date_of_death', sa.DateTime(), nullable=True),
        sa.Column('land_of_birth', sa.String(), nullable=True),
        sa.Column('land_of_birth_code', sa.String(), nullable=True),
        sa.Column('land_of_standing', sa.String(), nullable=True),
        sa.Column('size', sa.Float(), nullable=True),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('color_marking', sa.String(), nullable=True),
        sa.Column('eyes_color', sa.String(), nullable=True),
        sa.Column('variety', sa.String(), nullable=True),
        sa.Column('distinguishing_features', sa.String(), nullable=True),
        sa.Column('prefix_titles', sa.String(), nullable=True),
        sa.Column('suffix_titles', sa.String(), nullable=True),
        sa.Column('other_titles', sa.String(), nullable=True),
        sa.Column('registration_status', sa.Integer(), nullable=True),
        sa.Column('registration_number', sa.String(), nullable=True),
        sa.Column('brand_chip', sa.String(), nullable=True),
        sa.Column('coi', sa.Float(), nullable=True),
        sa.Column('coi_updated_on', sa.DateTime(), nullable=True),
        sa.Column('incomplete_pedigree', sa.Boolean(), nullable=True),
        sa.Column('photo_url', sa.String(), nullable=True),
        sa.Column('locked', sa.Boolean(), nullable=True),
        sa.Column('removed', sa.Boolean(), nullable=True),
        sa.Column('show_ad', sa.Boolean(), nullable=True),
        sa.Column('is_new', sa.Boolean(), nullable=True),
        sa.Column('modified', sa.Boolean(), nullable=True),
        sa.Column('modified_at', sa.DateTime(), nullable=True),
        sa.Column('health_info_general', sa.JSON(), nullable=True),
        sa.Column('health_info_genetic', sa.JSON(), nullable=True),
        sa.Column('neutered', sa.Boolean(), nullable=True),
        sa.Column('approved_for_breeding', sa.Boolean(), nullable=True),
        sa.Column('frozen_semen', sa.Boolean(), nullable=True),
        sa.Column('artificial_insemination', sa.Boolean(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('has_conflicts', sa.Boolean(), nullable=True),
        sa.Column('conflicts', sa.JSON(), nullable=True),
        sa.Column('kennel', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('data_correctness_notes', sa.String(), nullable=True),
        sa.Column('club', sa.String(), nullable=True),
        sa.Column('sports', sa.JSON(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dam_id', sa.Integer(), nullable=True),
        sa.Column('dam_uuid', sa.String(), nullable=True),
        sa.Column('dam_name', sa.String(), nullable=True),
        sa.Column('dam_link_name', sa.String(), nullable=True),
        sa.Column('sire_id', sa.Integer(), nullable=True),
        sa.Column('sire_uuid', sa.String(), nullable=True),
        sa.Column('sire_name', sa.String(), nullable=True),
        sa.Column('sire_link_name', sa.String(), nullable=True),
        sa.Column('birth_litter_id', sa.Integer(), nullable=True),  # ПОКА БЕЗ FOREIGN KEY
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dog_dam_id', 'dog', ['dam_id'], unique=False)
    op.create_index('ix_dog_sire_id', 'dog', ['sire_id'], unique=False)
    op.create_index(op.f('ix_dog_uuid'), 'dog', ['uuid'], unique=True)

    # 3. Создаем таблицу litter БЕЗ внешних ключей
    op.create_table('litter',
        sa.Column('date_of_birth', sa.DateTime(), nullable=True),
        sa.Column('litter_male_count', sa.Integer(), nullable=True),
        sa.Column('litter_female_count', sa.Integer(), nullable=True),
        sa.Column('litter_undef_count', sa.Integer(), nullable=True),
        sa.Column('sire_id', sa.Integer(), nullable=True),
        sa.Column('dam_id', sa.Integer(), nullable=True),
        sa.Column('mating_partner_id', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. Создаем остальные таблицы
    op.create_table('medical_record',
        sa.Column('registry', sa.String(), nullable=False),
        sa.Column('test_date', sa.DateTime(), nullable=True),
        sa.Column('report_date', sa.DateTime(), nullable=True),
        sa.Column('age_in_months', sa.Integer(), nullable=True),
        sa.Column('conclusion', sa.String(), nullable=True),
        sa.Column('ofa_number', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dog_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medical_record_dog_id'), 'medical_record', ['dog_id'], unique=False)
    op.create_index(op.f('ix_medical_record_ofa_number'), 'medical_record', ['ofa_number'], unique=False)
    op.create_index(op.f('ix_medical_record_registry'), 'medical_record', ['registry'], unique=False)

    op.create_table('mergelog',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dog_id', sa.Integer(), nullable=False),
        sa.Column('resolved_fields', sa.JSON(), nullable=True),
        sa.Column('old_values', sa.JSON(), nullable=True),
        sa.Column('new_values', sa.JSON(), nullable=True),
        sa.Column('conflicts', sa.JSON(), nullable=True),
        sa.Column('resolved_date', sa.DateTime(), nullable=False),
        sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('title',
        sa.Column('short_name', sa.String(), nullable=False),
        sa.Column('long_name', sa.String(), nullable=True),
        sa.Column('is_prefix', sa.Boolean(), nullable=False),
        sa.Column('has_winner_year', sa.Boolean(), nullable=True),
        sa.Column('winner_year', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dog_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 5. Создаем таблицы ассоциаций
    op.create_table('dogbreederlink',
        sa.Column('dog_id', sa.Integer(), nullable=False),
        sa.Column('breeder_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['breeder_id'], ['breeder.id'], ),
        sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], ),
        sa.PrimaryKeyConstraint('dog_id', 'breeder_id')
    )

    op.create_table('dogownerlink',
        sa.Column('dog_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['owner.id'], ),
        sa.PrimaryKeyConstraint('dog_id', 'owner_id')
    )

    op.create_table('dogsiblinglink',
        sa.Column('dog_id', sa.Integer(), nullable=False),
        sa.Column('sibling_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], ),
        sa.ForeignKeyConstraint(['sibling_id'], ['dog.id'], ),
        sa.PrimaryKeyConstraint('dog_id', 'sibling_id')
    )

    # 6. ТЕПЕРЬ добавляем оставшиеся внешние ключи
    # Добавляем внешний ключ dog.birth_litter_id -> litter.id
    op.create_foreign_key('fk_dog_birth_litter_id', 'dog', 'litter', ['birth_litter_id'], ['id'])

    # Добавляем внешние ключи litter -> dog
    op.create_foreign_key('fk_litter_sire_id', 'litter', 'dog', ['sire_id'], ['id'])
    op.create_foreign_key('fk_litter_dam_id', 'litter', 'dog', ['dam_id'], ['id'])
    op.create_foreign_key('fk_litter_mating_partner_id', 'litter', 'dog', ['mating_partner_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем в обратном порядке

    # Сначала внешние ключи
    op.drop_constraint('fk_litter_mating_partner_id', 'litter', type_='foreignkey')
    op.drop_constraint('fk_litter_dam_id', 'litter', type_='foreignkey')
    op.drop_constraint('fk_litter_sire_id', 'litter', type_='foreignkey')
    op.drop_constraint('fk_dog_birth_litter_id', 'dog', type_='foreignkey')

    # Затем таблицы ассоциаций
    op.drop_table('dogsiblinglink')
    op.drop_table('dogownerlink')
    op.drop_table('dogbreederlink')

    # Затем остальные таблицы
    op.drop_table('title')
    op.drop_table('mergelog')
    op.drop_index(op.f('ix_medical_record_registry'), table_name='medical_record')
    op.drop_index(op.f('ix_medical_record_ofa_number'), table_name='medical_record')
    op.drop_index(op.f('ix_medical_record_dog_id'), table_name='medical_record')
    op.drop_table('medical_record')

    # Основные таблицы
    op.drop_table('litter')
    op.drop_index(op.f('ix_dog_uuid'), table_name='dog')
    op.drop_index('ix_dog_sire_id', table_name='dog')
    op.drop_index('ix_dog_dam_id', table_name='dog')
    op.drop_table('dog')
    op.drop_index(op.f('ix_owner_uuid'), table_name='owner')
    op.drop_table('owner')
    op.drop_index(op.f('ix_breeder_uuid'), table_name='breeder')
    op.drop_table('breeder')
