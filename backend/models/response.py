from typing import List, Generic, TypeVar, Optional
from sqlmodel import SQLModel

T = TypeVar('T')

class PaginationMeta(SQLModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    has_more: bool

class DogListResponse(SQLModel):
    data: List['Dog']
    meta: PaginationMeta

class PedigreeNode(SQLModel):
    id: int
    name: str
    dam: Optional['PedigreeNode']
    sire: Optional['PedigreeNode']