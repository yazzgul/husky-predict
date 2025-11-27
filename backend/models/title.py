from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, Any
from datetime import datetime

class TitleBase(SQLModel):
    short_name: str
    long_name: Optional[str]
    is_prefix: bool
    has_winner_year: Optional[bool] = False
    winner_year: Optional[int]

class Title(TitleBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Явное объявление столбца dog_id
    dog_id: int = Field(foreign_key="dog.id")
    dog: Optional["Dog"] = Relationship(back_populates="titles")


    @classmethod
    def validate(cls, data: Any) -> 'Title':
        if isinstance(data, cls):
            return data
        if isinstance(data, dict):
            return cls(**data)
        raise ValueError(f"Invalid data type for {cls.__name__}: {type(data)}")

class TitleCreate(TitleBase):
    pass

class TitleRead(SQLModel):
    id: Optional[int]
    dog_id: int
    short_name: str
    long_name: Optional[str]
    is_prefix: bool
    has_winner_year: Optional[bool] = False
    winner_year: Optional[int]

    class Config:
        from_attributes = True