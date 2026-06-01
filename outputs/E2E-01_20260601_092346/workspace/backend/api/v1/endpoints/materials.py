from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from backend import schemas, services
from backend.database import get_db

router = APIRouter(
    prefix="/materials",
    tags=["Materials"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.MaterialResponse, status_code=status.HTTP_201_CREATED)
def create_material(material: schemas.MaterialCreate, db: Session = Depends(get_db)):
    """
    Create a new material and its initial inventory.
    """
    return services.material_service.create_material(db=db, material=material)

@router.get("/", response_model=List[schemas.MaterialResponse])
def read_materials(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of materials.
    """
    materials = services.material_service.get_materials(db, skip=skip, limit=limit)
    return materials

@router.get("/{material_id}", response_model=schemas.MaterialResponse)
def read_material(material_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single material by ID.
    """
    material = services.material_service.get_material_by_id(db, material_id=material_id)
    return material