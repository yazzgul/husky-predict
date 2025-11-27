from .dogs import router as dogs_router
from .breedarchive import router as breedarchive_router
from .breedbase import router as breedbase_router
from .huskypedigree import router as huskypedigree_router
from .pedigree import router as pedigree_router
from .ofa import router as ofa_router


# "pedigree_router"
__all__ = ["dogs_router", "breedbase_router", "breedarchive_router", "huskypedigree_router", "pedigree_router", "ofa_router"]