from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from backend import models, schemas

def get_materials(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Material).offset(skip).limit(limit).all()

def get_material_by_id(db: Session, material_id: int):
    material = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material

def create_material(db: Session, material: schemas.MaterialCreate):
    db_material = db.query(models.Material).filter(models.Material.name == material.name).first()
    if db_material:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Material with this name already exists")

    db_material = models.Material(name=material.name, description=material.description)
    db.add(db_material)
    db.commit()
    db.refresh(db_material)

    # Create initial inventory for the new material
    db_inventory = models.Inventory(
        material_id=db_material.id,
        quantity=material.initial_inventory_quantity
    )
    db.add(db_inventory)
    db.commit()
    db.refresh(db_inventory)

    return db_material