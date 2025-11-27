from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, DateTime, Integer, ForeignKey
from typing import Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .dog import Dog

class MedicalRecordBase(SQLModel):

    # Registry - какой орган / часть тела тестировалась
    registry: str = Field(index=True)

    # Test Date - дата проведения
    test_date: Optional[datetime] = Field(default=None)

    # Report Date - дата репорта теста
    report_date: Optional[datetime] = Field(default=None)

    # AgeInMonth - возраст в месяцах
    age_in_months: Optional[int] = Field(default=None)

    # Conclusion - заключение
    conclusion: Optional[str] = Field(default=None)

    # OFA Number - номер обследования
    ofa_number: Optional[str] = Field(default=None, index=True)

    # Source of the medical record
    source: str = Field(default="ofa.org")

    # Additional notes
    notes: Optional[str] = Field(default=None)

class MedicalRecord(MedicalRecordBase, table=True):

    __tablename__ = "medical_record"

    id: int = Field(default=None, primary_key=True)

    # Foreign key to Dog
    dog_id: Optional[int] = Field(
        default=None,
        foreign_key="dog.id",
        index=True
    )

    # Relationship to Dog
    dog: Optional["Dog"] = Relationship(
        back_populates="medical_records",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "foreign_keys": "MedicalRecord.dog_id"
        }
    )

class MedicalRecordCreate(MedicalRecordBase):
    pass

class MedicalRecordRead(MedicalRecordBase):
    id: Optional[int]
    dog_id: int
    registry: str
    test_date: Optional[datetime]
    report_date: Optional[datetime]
    age_in_months: Optional[int]
    conclusion: Optional[str]
    ofa_number: Optional[str]
    source: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True