from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.schemas import InventoryCreate, InventoryUpdate, Inventory as InventorySchema
from backend.services import InventoryService
from typing import List

router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
    responses={404: {"model": dict, "description": "Not found"}},
)

@router.post("/", response_model=InventorySchema, status_code=status.HTTP_201_CREATED, summary="Create a new inventory item")
async def create_inventory(
    inventory: InventoryCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    새로운 재고 항목을 생성합니다.
    """
    service = InventoryService(db)
    try:
        return await service.create_inventory(inventory)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/", response_model=List[InventorySchema], summary="Get a list of inventory items")
async def read_inventory(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    모든 재고 항목 목록을 조회합니다.
    """
    service = InventoryService(db)
    inventory_items = await service.get_inventory(skip=skip, limit=limit)
    return inventory_items

@router.get("/{inventory_id}", response_model=InventorySchema, summary="Get a specific inventory item by ID")
async def read_inventory_item(
    inventory_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 재고 항목 ID로 재고 정보를 조회합니다.
    """
    service = InventoryService(db)
    try:
        return await service.get_inventory_item(inventory_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.patch("/{inventory_id}", response_model=InventorySchema, summary="Update an existing inventory item")
async def update_inventory(
    inventory_id: int,
    inventory_update: InventoryUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 재고 항목 ID의 정보를 업데이트합니다.
    """
    service = InventoryService(db)
    try:
        return await service.update_inventory(inventory_id, inventory_update)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.delete("/{inventory_id}", response_model=InventorySchema, summary="Delete an inventory item by ID")
async def delete_inventory(
    inventory_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 재고 항목 ID로 재고를 삭제합니다.
    """
    service = InventoryService(db)
    try:
        return await service.delete_inventory(inventory_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

print("Inventory router defined.")