from sqlmodel import SQLModel, Field, Relationship
from typing import Optional

class DogBreederLink(SQLModel, table=True):
    _tablename__ = "dogbreederlink"

    dog_id: Optional[int] = Field(
        default=None, 
        foreign_key="dog.id", 
        primary_key=True
    )
    breeder_id: Optional[int] = Field(
        default=None, 
        foreign_key="breeder.id", 
        primary_key=True
    )
    dog: "Dog" = Relationship(
        back_populates="breeders_assoc",
        sa_relationship_kwargs={
            "overlaps": "breeders,dogs,breeder"
        }
    )
    breeder: "Breeder" = Relationship(
        back_populates="dogs_assoc",
        sa_relationship_kwargs={
            "overlaps": "dogs,dog,breeder"
        }
    )

class DogOwnerLink(SQLModel, table=True):
    _tablename__ = "dogownerlink"

    dog_id: Optional[int] = Field(
        default=None, 
        foreign_key="dog.id", 
        primary_key=True
    )
    owner_id: Optional[int] = Field(
        default=None, 
        foreign_key="owner.id", 
        primary_key=True
    )
    dog: "Dog" = Relationship(
        back_populates="owners_assoc",
        sa_relationship_kwargs={
            "overlaps": "owners,dogs,owner"
        }
    )
    owner: "Owner" = Relationship(
        back_populates="dogs_assoc",
        sa_relationship_kwargs={
            "overlaps": "dogs,dog,owner"
        }
    )
