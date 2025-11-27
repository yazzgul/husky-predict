from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON
from typing import Optional
from datetime import datetime

class MergeLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dog_id: int = Field(foreign_key="dog.id")
    resolved_fields: Optional[dict] = Field(sa_column=Column(JSON))
    old_values: Optional[dict] = Field(sa_column=Column(JSON))
    new_values: Optional[dict] = Field(sa_column=Column(JSON))
    conflicts: Optional[dict] = Field(sa_column=Column(JSON))
    resolved_date: datetime = Field(default_factory=datetime.utcnow)
    resolved_by_user_id: Optional[int] = Field(default=None, nullable=True)

    dog: Optional["Dog"] = Relationship(back_populates="merge_logs")

class MergeLogRead(SQLModel):
    id: Optional[int]
    dog_id: int
    resolved_fields: Optional[dict]
    old_values: Optional[dict]
    new_values: Optional[dict]
    conflicts: Optional[dict]
    resolved_date: Optional[datetime]
    resolved_by_user_id: Optional[int]

    class Config:
        from_attributes = True