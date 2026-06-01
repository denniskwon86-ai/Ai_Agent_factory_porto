from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.schemas import MaterialCreate, MaterialUpdate, Material as MaterialSchema
from backend.services import MaterialService
from typing import List

router = APIRouter(
    prefix="/materials",
    tags=["Materials"],
    responses={404: {"model": dict, "description": "Not found"}},
)

@router.post("/", response_model=MaterialSchema, status_code=status.HTTP_201_CREATED, summary="Create a new material")
async def create_material(
    material: MaterialCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    새로운 자재(Material)를 생성합니다.
    """
    service = MaterialService(db)
    try:
        return await service.create_material(material)
    except HTTPException as e:
        raise e
    except Exception as e:
        # 로깅 추가 권장
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/", response_model=List[MaterialSchema], summary="Get a list of materials")
async def read_materials(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    모든 자재(Material) 목록을 조회합니다.
    """
    service = MaterialService(db)
    materials = await service.get_materials(skip=skip, limit=limit)
    return materials

@router.get("/{material_id}", response_model=MaterialSchema, summary="Get a specific material by ID")
async def read_material(
    material_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 자재(Material) ID로 자재 정보를 조회합니다.
    """
    service = MaterialService(db)
    try:
        return await service.get_material(material_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.patch("/{material_id}", response_model=MaterialSchema, summary="Update an existing material")
async def update_material(
    material_id: int,
    material_update: MaterialUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 자재(Material) ID의 정보를 업데이트합니다.
    """
    service = MaterialService(db)
    try:
        return await service.update_material(material_id, material_update)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.delete("/{material_id}", response_model=MaterialSchema, summary="Delete a material by ID")
async def delete_material(
    material_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 자재(Material) ID로 자재를 삭제합니다.
    """
    service = MaterialService(db)
    try:
        return await service.delete_material(material_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

print("Material router defined.")