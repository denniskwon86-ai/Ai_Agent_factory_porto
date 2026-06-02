from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db, Base, engine
from backend.schemas.material_schema import MaterialCreate, MaterialResponse
from backend.schemas.common_schema import ErrorResponse
from backend.services.material_service import material_service
from backend.core.exceptions import NotFoundException, ConflictException

router = APIRouter(
    prefix="/materials",
    tags=["Materials"],
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Not Found"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflict"}
    }
)

@router.post("/", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
def create_material_endpoint(material: MaterialCreate, db: Session = Depends(get_db)):
    """
    Create a new material.
    """
    return material_service.create_material(db=db, material=material)

@router.get("/", response_model=List[MaterialResponse])
def read_materials_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of materials.
    """
    materials = material_service.get_materials(db, skip=skip, limit=limit)
    return materials

@router.get("/{material_id}", response_model=MaterialResponse)
def read_material_endpoint(material_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single material by ID.
    """
    return material_service.get_material(db, material_id=material_id)