from sqlmodel import SQLModel, ForeignKeyConstraint, Field, Relationship
from sqlalchemy import Column, Date
from datetime import datetime
from typing import Optional, List

class LitterBase(SQLModel):
    date_of_birth: Optional[datetime] = Field(default=None, sa_column=Column(Date))
    litter_male_count: int = 0
    litter_female_count: int = 0
    litter_undef_count: int = 0
    dam_id: Optional[int] = Field(foreign_key="dog.id")
    sire_id: Optional[int] = Field(foreign_key="dog.id")
    mating_partner_id: Optional[int] = Field(foreign_key="dog.id")

class Litter(LitterBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date_of_birth: Optional[datetime] = None
    litter_male_count: Optional[int] = 0
    litter_female_count: Optional[int] = 0
    litter_undef_count: Optional[int] = 0

    # Relationships
    sire_id: Optional[int] = Field(default=None, foreign_key="dog.id")
    dam_id: Optional[int] = Field(default=None, foreign_key="dog.id")
    mating_partner_id: Optional[int] = Field(default=None, foreign_key="dog.id")

    sire: Optional["Dog"] = Relationship(
        back_populates="litters_as_sire",
        sa_relationship_kwargs={"foreign_keys": "Litter.sire_id"}
    )
    dam: Optional["Dog"] = Relationship(
        back_populates="litters_as_dam",
        sa_relationship_kwargs={"foreign_keys": "Litter.dam_id"}
    )
    mating_partner: Optional["Dog"] = Relationship(
        back_populates="litters_as_mating_partner",
        sa_relationship_kwargs={"foreign_keys": "Litter.mating_partner_id"}
    )
    puppies: List["Dog"] = Relationship(
        back_populates="birth_litter",
        sa_relationship_kwargs={"foreign_keys": "Dog.birth_litter_id"}
    )

class LitterCreate(LitterBase):
    pass

class LitterRead(LitterBase):
    id: Optional[int]
    date_of_birth: Optional[datetime]
    litter_male_count: Optional[int]
    litter_female_count: Optional[int]
    litter_undef_count: Optional[int]
    sire_id: Optional[int]
    dam_id: Optional[int]
    mating_partner_id: Optional[int]

    class Config:
        from_attributes = True