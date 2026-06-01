from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from backend.models import Inventory, Material
from backend.schemas import InventoryCreate, InventoryUpdate, Inventory as InventorySchema
from typing import List, Optional

class InventoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_inventory(self, inventory: InventoryCreate) -> InventorySchema:
        """새로운 재고 항목을 생성합니다."""
        # 자재 존재 여부 확인
        material_result = await self.db.execute(
            select(Material).filter(Material.material_id == inventory.material_id)
        )
        if not material_result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Material not found")

        db_inventory = Inventory(
            material_id=inventory.material_id,
            quantity=inventory.quantity,
            location=inventory.location
        )
        self.db.add(db_inventory)
        await self.db.commit()
        await self.db.refresh(db_inventory)
        return InventorySchema.from_orm(db_inventory)

    async def get_inventories(self, skip: int = 0, limit: int = 100) -> List[InventorySchema]:
        """모든 재고 항목 목록을 조회합니다."""
        result = await self.db.execute(
            select(Inventory).options(joinedload(Inventory.material)).offset(skip).limit(limit)
        )
        inventories = result.scalars().all()
        return [InventorySchema.from_orm(inv) for inv in inventories]

    async def get_inventory(self, inventory_id: int) -> InventorySchema:
        """특정 재고 항목 ID로 재고 정보를 조회합니다."""
        result = await self.db.execute(
            select(Inventory).options(joinedload(Inventory.material)).filter(Inventory.inventory_id == inventory_id)
        )
        inventory = result.scalars().first()
        if not inventory:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found")
        return InventorySchema.from_orm(inventory)

    async def update_inventory(self, inventory_id: int, inventory_update: InventoryUpdate) -> InventorySchema:
        """특정 재고 항목 ID로 재고 정보를 업데이트합니다."""
        result = await self.db.execute(
            select(Inventory).filter(Inventory.inventory_id == inventory_id)
        )
        db_inventory = result.scalars().first()
        if not db_inventory:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found")

        # 자재 ID 변경 시 유효성 검사
        if inventory_update.material_id is not None and inventory_update.material_id != db_inventory.material_id:
            material_result = await self.db.execute(
                select(Material).filter(Material.material_id == inventory_update.material_id)
            )
            if not material_result.scalars().first():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New material not found")

        for key, value in inventory_update.dict(exclude_unset=True).items():
            setattr(db_inventory, key, value)

        await self.db.commit()
        await self.db.refresh(db_inventory)
        return InventorySchema.from_orm(db_inventory)

    async def delete_inventory(self, inventory_id: int) -> InventorySchema:
        """특정 재고 항목 ID로 재고를 삭제합니다."""
        result = await self.db.execute(
            select(Inventory).filter(Inventory.inventory_id == inventory_id)
        )
        db_inventory = result.scalars().first()
        if not db_inventory:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found")

        await self.db.delete(db_inventory)
        await self.db.commit()
        return InventorySchema.from_orm(db_inventory)

print("InventoryService defined.")