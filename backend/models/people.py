
from sqlmodel import SQLModel, Field, Relationship
from typing import List, Optional, Any

from .associations import DogBreederLink, DogOwnerLink

class Breeder(SQLModel, table=True):
    __tablename__ = "breeder"
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: Optional[str] = Field(unique=True, index=True)
    name: str
    is_breeder: bool
    
    dogs: List["Dog"] = Relationship(
        back_populates="breeders",
        link_model=DogBreederLink,
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "dogs_assoc,dog,breeder"
        }
    )
    dogs_assoc: List["DogBreederLink"] = Relationship(
        back_populates="breeder", 
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "dogs,dog,breeder"
        }
    )
    
    @classmethod
    def validate(cls, data: Any) -> 'Breeder':
        if isinstance(data, cls):
            return data
        if isinstance(data, dict):
            return cls(**data)
        raise ValueError(f"Invalid data type for {cls.__name__}: {type(data)}")

class Owner(SQLModel, table=True):
    __tablename__ = "owner"
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: Optional[str] = Field(unique=True, index=True)
    name: str
    is_main_owner: bool
    
    dogs: List["Dog"] = Relationship(
        back_populates="owners",
        link_model=DogOwnerLink,
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "dogs_assoc,dog,owner"
        }
    )
    dogs_assoc: List["DogOwnerLink"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "overlaps": "dogs,dog,owner"
        }
    )
    
    @classmethod
    def validate(cls, data: Any) -> 'Owner':
        if isinstance(data, cls):
            return data
        if isinstance(data, dict):
            return cls(**data)
        raise ValueError(f"Invalid data type for {cls.__name__}: {type(data)}")

class BreederRead(SQLModel):
    id: Optional[int]
    uuid: str
    name: str
    is_breeder: bool = True

    class Config:
        from_attributes = True

class OwnerRead(SQLModel):
    id: Optional[int]
    uuid: str
    name: str
    is_main_owner: bool = True

    class Config:
        from_attributes = True
