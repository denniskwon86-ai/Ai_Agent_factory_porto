from sqlalchemy.orm import Session
from backend.models.material import Material
from backend.schemas.material_schema import MaterialCreate
from backend.core.exceptions import NotFoundException, ConflictException

class MaterialService:
    def get_material(self, db: Session, material_id: int) -> Material:
        material = db.query(Material).filter(Material.material_id == material_id).first()
        if not material:
            raise NotFoundException(detail=f"Material with id {material_id} not found")
        return material

    def get_material_by_code(self, db: Session, material_code: str) -> Material:
        material = db.query(Material).filter(Material.material_code == material_code).first()
        if not material:
            raise NotFoundException(detail=f"Material with code {material_code} not found")
        return material

    def get_materials(self, db: Session, skip: int = 0, limit: int = 100) -> list[Material]:
        return db.query(Material).offset(skip).limit(limit).all()

    def create_material(self, db: Session, material: MaterialCreate) -> Material:
        db_material = db.query(Material).filter(Material.material_code == material.material_code).first()
        if db_material:
            raise ConflictException(detail=f"Material with code {material.material_code} already exists")
        
        db_material = Material(
            material_code=material.material_code,
            material_name=material.material_name,
            unit_of_measure=material.unit_of_measure
        )
        db.add(db_material)
        db.commit()
        db.refresh(db_material)
        return db_material

material_service = MaterialService()