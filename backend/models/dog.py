
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import JSON, Column, DateTime, Index, Integer, ForeignKeyConstraint
from typing import Optional, List, Dict, Union, TYPE_CHECKING
from datetime import datetime, date
# from pydantic import validator

from models.response import PaginationMeta

from .associations import DogBreederLink, DogOwnerLink
from .people import Breeder, Owner
from .litters import Litter
from .title import Title
from .merge_log import MergeLog
from .merge_log import MergeLogRead
from .medicalRecord import MedicalRecordRead
from .title import TitleRead
from .people import BreederRead, OwnerRead
from .litters import LitterRead

if TYPE_CHECKING:
    from .medicalRecord import MedicalRecord

class DogBase(SQLModel):
    # Identifiers & Names
    uuid: str = Field(unique=True, index=True)
    registered_name: Optional[str]
    call_name: Optional[str]
    link_name: Optional[str]

    # Demographics
    sex: int  # 1 - Male, 2 - Female
    year_of_birth: Optional[int]
    month_of_birth: Optional[int]
    day_of_birth:  Optional[int]
    date_of_birth: Optional[datetime]

    year_of_death: Optional[int]
    month_of_death: Optional[int]
    day_of_death:  Optional[int]
    date_of_death: Optional[datetime]

    land_of_birth: Optional[str]
    land_of_birth_code: Optional[str]
    land_of_standing: Optional[str]

    # Appearance
    size: Optional[float]
    weight: Optional[float]
    color: Optional[str]
    color_marking: Optional[str]
    eyes_color: Optional[str]
    variety: Optional[str]
    distinguishing_features: Optional[str] # отличительные признаки

    # Titles
    prefix_titles: Optional[str]
    suffix_titles: Optional[str]
    other_titles: Optional[str]

    # Registration
    registration_status: Optional[int]
    registration_number: Optional[str]
    brand_chip: Optional[str]

    # Pedigree
    coi: Optional[float]
    coi_updated_on: Optional[datetime]
    incomplete_pedigree: Optional[bool]

    # Photos
    photo_url: Optional[str]

    # Status flags
    locked: Optional[bool]
    removed: Optional[bool]
    show_ad: Optional[bool]
    is_new: Optional[bool]
    modified: Optional[bool]

    # Timestamps
    modified_at: Optional[datetime]

    # Health
    health_info_general: Optional[List[Dict]] = Field(sa_column=Column(JSON))  # breed_relevant
    health_info_genetic: Optional[List[Dict]] = Field(sa_column=Column(JSON)) # other_screenings
    neutered: Optional[bool]
    approved_for_breeding: Optional[bool] # stud_animal
    frozen_semen: Optional[bool]
    artificial_insemination: Optional[bool]

    # Source
    source: Optional[str] = "breedarchive.com"

    # Conflict tracking
    has_conflicts: Optional[bool] = Field(default=False)
    conflicts: Optional[Dict] = Field(sa_column=Column(JSON), default=None)

    # Данные о владельце / заводчиках / питомнике
    kennel: Optional[str]

    # Доп. инфо
    notes: Optional[str]
    data_correctness_notes: Optional[str]
    club: Optional[str]
    sports: Optional[List[str]] = Field(
        sa_column=Column(JSON),
        default=None
    )

    # # Валидаторы
    # @validator("coi", pre=True)
    # def parse_coi(cls, v):
    #     if isinstance(v, str):
    #         try:
    #             return float(v)
    #         except ValueError:
    #             return None
    #     return v

    # @validator("year_of_birth", "year_of_death", pre=True)
    # def parse_year(cls, v):
    #     if isinstance(v, str):
    #         if v.strip() == "":
    #             return None
    #         try:
    #             return int(v)
    #         except ValueError:
    #             return None
    #     return v

    # @validator("modified_at", pre=True)
    # def parse_modified_at(cls, v):
    #     if isinstance(v, str):
    #         try:
    #             return datetime.strptime(v, "%m/%d/%Y, %H:%M")
    #         except ValueError:
    #             return None
    #     return v

    # @validator("health_info_general", "health_info_genetic", "sports", pre=True)
    # def parse_json_fields(cls, value):
    #     if isinstance(value, str):
    #         try:
    #             return json.loads(value)
    #         except json.JSONDecodeError:
    #             return None
    #     return value

# Ассоциативные таблицы для связей Many-to-Many
class DogSiblingLink(SQLModel, table=True):
    dog_id: Optional[int] = Field(
        default=None,
        foreign_key="dog.id",
        primary_key=True
    )
    sibling_id: Optional[int] = Field(
        default=None,
        foreign_key="dog.id",
        primary_key=True
    )
    dog: "Dog" = Relationship(
        back_populates="siblings_assoc",
        sa_relationship_kwargs={
            "foreign_keys": "DogSiblingLink.dog_id"
        }
    )
    sibling: "Dog" = Relationship(
        back_populates="siblings_assoc",
        sa_relationship_kwargs={
            "foreign_keys": "DogSiblingLink.sibling_id"
        }
    )

class Dog(DogBase, table=True):
    __table_args__ = (
        Index('ix_dog_dam_id', 'dam_id'),
        Index('ix_dog_sire_id', 'sire_id'),
        # Явное имя для внешнего ключа birth_litter_id
        ForeignKeyConstraint(
            ["birth_litter_id"], ["litter.id"],
            name="fk_dog_birth_litter_id"
        ),
    )
    id: int = Field(default=None, primary_key=True)
    # Relationships
    dam_id: Optional[int] = Field(
        default=None,
        foreign_key="dog.id",
    )
    dam: Optional["Dog"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "remote_side": "Dog.id",
            "foreign_keys": "[Dog.dam_id]"
        },
        back_populates="children_as_dam"
    )
    dam_uuid: Optional[str] = Field(
        default=None,
        nullable=True
    ) # Ссылка на родителя по UUID c исходного источника, а не в нашей базе
    dam_name: Optional[str]
    dam_link_name: Optional[str]

    sire_id: Optional[int] = Field(
        default=None,
        foreign_key="dog.id"
    )
    sire: Optional["Dog"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "remote_side": "Dog.id",
            "foreign_keys": "[Dog.sire_id]"
        },
        back_populates="children_as_sire"
    )
    sire_uuid: Optional[str] = Field(
        default=None,
        nullable=True
    ) # Ссылка на родителя по UUID c исходного источника, а не в нашей базе
    sire_name: Optional[str]
    sire_link_name: Optional[str]

    children_as_dam: Optional[List["Dog"]] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Dog.dam_id]"},
        back_populates="dam"
    )
    children_as_sire: Optional[List["Dog"]] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Dog.sire_id]"},
        back_populates="sire"
    )

    # Связь с пометом рождения
    birth_litter_id: Optional[int] = Field(foreign_key="litter.id")
    birth_litter: Optional["Litter"] = Relationship(
        back_populates="puppies",
        sa_relationship_kwargs={
            "foreign_keys": "Dog.birth_litter_id"
        }
    )
    litters_as_dam: Optional[List["Litter"]] = Relationship(
        back_populates="dam",
        sa_relationship_kwargs={
            "foreign_keys": "Litter.dam_id"
        }
    )
    litters_as_sire: Optional[List["Litter"]] = Relationship(
        back_populates="sire",
        sa_relationship_kwargs={
            "foreign_keys": "Litter.sire_id"
        }
    )

    litters_as_mating_partner: Optional[List["Litter"]] = Relationship(
        back_populates="mating_partner",
        sa_relationship_kwargs={
            "foreign_keys": "Litter.mating_partner_id"
        }
    )

    # Связи, если собака - брат/сестра
    siblings: Optional[List["Dog"]] = Relationship(
        back_populates="siblings",
        link_model=DogSiblingLink,
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "siblings_assoc,dog,sibling",
            "primaryjoin": "Dog.id == DogSiblingLink.dog_id",
            "secondaryjoin": "DogSiblingLink.sibling_id == Dog.id",
            "foreign_keys": "[DogSiblingLink.dog_id, DogSiblingLink.sibling_id]"
        }
    )
    siblings_assoc: List["DogSiblingLink"] = Relationship(
        back_populates="dog",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "foreign_keys": "DogSiblingLink.dog_id",
            "overlaps": "siblings,sibling"  # Исправлен overlaps
        }
    )


    # Связи с людьми и титулы
    titles: List[Title] = Relationship(
        back_populates="dog",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "foreign_keys": "Title.dog_id",
        }
    )

    breeders: List[Breeder] = Relationship(
        back_populates="dogs",
        link_model=DogBreederLink,
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "breeders_assoc,dog,breeder"
        }
    )
    owners: List[Owner] = Relationship(
        back_populates="dogs",
        link_model=DogOwnerLink,
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "owners_assoc,dog,owner,dogs_assoc"
        }
    )

    breeders_assoc: List["DogBreederLink"] = Relationship(
        back_populates="dog",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "breeders,dogs,breeder"
        }
    )
    owners_assoc: List["DogOwnerLink"] = Relationship(
        back_populates="dog",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "owners,dogs,owner"
        }
    )
    medical_records: List["MedicalRecord"] = Relationship(
        back_populates="dog",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "foreign_keys": "MedicalRecord.dog_id"
        }
    )
    merge_logs: List[MergeLog] = Relationship(
        back_populates="dog",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "foreign_keys": "MergeLog.dog_id"
        }
    )

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class DogCreate(DogBase):
    # dam_uuid: Optional[str]
    # sire_uuid: Optional[str]
    breeders: Optional[List[Breeder]] = []
    owners: Optional[List[Owner]] = []
    titles: Optional[List[Title]] = []
    siblings: Optional[List[Dog]] = []
    litters: Optional[List[Litter]] = []

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        # schema_extra = {
        #     "example": {
        #         "id": 1,
        #         "uuid": "550e8400-e29b-41d4-a716-446655440000",
        #         "registered_name": "Champion's Bloodline",
        #         # ... остальные поля
        #     }
        # }

    # @validator('dam', 'sire', pre=True)
    # def prevent_nested_loops(cls, v):
    #     if isinstance(v, Dog):
    #         return DogRead(
    #             **v.dict(exclude={"dam", "sire"}),
    #             dam=None,
    #             sire=None
    #         )
    #     return v

class DogRead(DogBase):
    id: int
    dam_id: Optional[int]
    dam_uuid: Optional[str]
    dam_name: Optional[str]
    dam_link_name: Optional[str]
    sire_id: Optional[int]
    sire_uuid: Optional[str]
    sire_name: Optional[str]
    sire_link_name: Optional[str]
    birth_litter_id: Optional[int]

    # Связи с родителями (только ID и базовые поля, чтобы избежать рекурсии)
    dam: Optional["DogRead"] = None
    sire: Optional["DogRead"] = None

    # Связи с пометами
    birth_litter: Optional[LitterRead] = None
    litters_as_dam: Optional[List[LitterRead]] = []
    litters_as_sire: Optional[List[LitterRead]] = []
    litters_as_mating_partner: Optional[List[LitterRead]] = []

    # Связи с братьями/сестрами (только ID и базовые поля)
    siblings: Optional[List["DogRead"]] = []

    # Связи с людьми и титулы
    titles: Optional[List[TitleRead]] = []
    breeders: Optional[List[BreederRead]] = []
    owners: Optional[List[OwnerRead]] = []

    # Медицинские записи и логи слияния
    medical_records: Optional[List[MedicalRecordRead]] = []
    merge_logs: Optional[List[MergeLogRead]] = []

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

# Упрощенная модель для избежания циклических ссылок
class DogReadSimple(SQLModel):
    id: int
    uuid: str
    registered_name: Optional[str]
    call_name: Optional[str]
    sex: int
    date_of_birth: Optional[datetime]
    color: Optional[str]
    source: Optional[str]
    has_conflicts: Optional[bool]
    dam_id: Optional[int]
    sire_id: Optional[int]
    dam_name: Optional[str]
    sire_name: Optional[str]

    class Config:
        from_attributes = True

# Обновляем DogRead для использования упрощенных моделей
class DogRead(DogBase):
    id: int
    dam_id: Optional[int]
    dam_uuid: Optional[str]
    dam_name: Optional[str]
    dam_link_name: Optional[str]
    sire_id: Optional[int]
    sire_uuid: Optional[str]
    sire_name: Optional[str]
    sire_link_name: Optional[str]
    birth_litter_id: Optional[int]

    # Связи с родителями (упрощенные модели)
    dam: Optional[DogReadSimple] = None
    sire: Optional[DogReadSimple] = None

    # Связи с пометами
    birth_litter: Optional[LitterRead] = None
    litters_as_dam: Optional[List[LitterRead]] = []
    litters_as_sire: Optional[List[LitterRead]] = []
    litters_as_mating_partner: Optional[List[LitterRead]] = []

    # Связи с братьями/сестрами (упрощенные модели)
    siblings: Optional[List[DogReadSimple]] = []

    # Связи с людьми и титулы
    titles: Optional[List[TitleRead]] = []
    breeders: Optional[List[BreederRead]] = []
    owners: Optional[List[OwnerRead]] = []

    # Медицинские записи и логи слияния
    medical_records: Optional[List[MedicalRecordRead]] = []
    merge_logs: Optional[List[MergeLogRead]] = []

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class DogListResponse(SQLModel):
    data: List[DogRead]
    meta: 'PaginationMeta'
